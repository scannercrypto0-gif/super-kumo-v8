"""P2-A public historical development intake, not a strategy/backtest engine.

Reuses B1's strict native archive parser only. No P0/P1 runner or arm inference.
Raw source remains private; all source availability/correction clocks are unknown.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import tempfile
import urllib.error
import urllib.request
import zipfile

from .aql_b1_market_research import parse_archive, BASE, BAR_MS

EMBARGO_MS = 72 * 3600000
HOLDOUT_START = 1761955200000  # 2025-11-01 UTC, intentionally not fetched
HOLDOUT_END = 1764547200000    # 2025-12-01 UTC
MAX_BYTES = 32 * 1024 * 1024
INDEX_SCHEMA = 'aql.p2-historical-bar-index.v1'


class IntakeError(ValueError):
    pass


class AccessDenied(IntakeError):
    pass


def require(ok, reason):
    if not ok:
        raise IntakeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()


def parse(raw):
    def pairs(items):
        obj = {}
        for k, v in items:
            require(k not in obj, 'DUPLICATE_JSON_KEY')
            obj[k] = v
        return obj
    def reject(_):
        raise IntakeError('NONFINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def utc_ms(text):
    require(isinstance(text, str) and text.endswith('Z'), 'UTC_Z_REQUIRED')
    d = datetime.fromisoformat(text.replace('Z', '+00:00'))
    require(d.utcoffset().total_seconds() == 0, 'UTC_ONLY')
    return int(d.timestamp() * 1000)


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def guard_development(start, end, plan):
    require(type(start) is int and type(end) is int and start < end, 'INVALID_PERIOD')
    require(plan['phase'] == 'DEVELOPMENT_ONLY', 'HOLDOUT_PHASE_DENIED')
    require(type(plan['embargo_ms']) is int and plan['embargo_ms'] >= EMBARGO_MS, 'EMBARGO_BELOW_72H')
    require(end <= HOLDOUT_START - plan['embargo_ms'] or start >= HOLDOUT_END + plan['embargo_ms'],
            'SEALED_HOLDOUT_OR_EMBARGO_DENIED')


def validate_plan(plan):
    require(plan['schema'] == 'aql.p2a-frozen-development-plan.v1', 'PLAN_SCHEMA')
    require((plan['source_exchange'], plan['source_market'], plan['symbol'], plan['interval_ms'],
             plan['availability_mode']) == ('BINANCE', 'SPOT', 'BTCUSDT', BAR_MS, 'RETROSPECTIVE_NON_PIT'),
            'PLAN_SOURCE_OR_SCOPE_DRIFT')
    require(utc_ms(plan['sealed_holdout']['start_utc']) == HOLDOUT_START
            and utc_ms(plan['sealed_holdout']['end_exclusive_utc']) == HOLDOUT_END
            and plan['sealed_holdout']['status'] == 'SEALED_NO_FETCH_NO_EVALUATION', 'HOLDOUT_BOUNDARY_DRIFT')
    require(plan['base_registration'] is None and plan['shadow_registration'] is None,
            'UNSUPPORTED_ARM_REGISTRATION_USE_CORE_CONTRACT')
    utc_ms(plan['declared_at_utc'])
    require(plan['terms']['license'] == 'CC BY-NC-SA 4.0'
            and plan['terms']['commercial_or_trading_rights_granted'] is False, 'TERMS_SCOPE_REQUIRED')
    windows = plan['development_windows']
    require(len(windows) >= 2, 'MULTIPERIOD_REQUIRED')
    seen, periods = set(), []
    for w in windows:
        require(w['dataset_id'] not in seen, 'DUPLICATE_DATASET')
        seen.add(w['dataset_id'])
        start, end = utc_ms(w['start_utc']), utc_ms(w['end_exclusive_utc'])
        guard_development(start, end, plan)
        d = datetime.fromtimestamp(start / 1000, timezone.utc)
        require(d.year in (2023, 2024) and d.day == 1 and d.hour == d.minute == d.second == d.microsecond == 0,
                'ONLY_EXPLICIT_2023_2024_NATIVE_MILLISECONDS_SUPPORTED')
        next_month = datetime(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1, tzinfo=timezone.utc)
        require(end == int(next_month.timestamp() * 1000), 'FULL_MONTH_REQUIRED')
        item = w['source']
        name = f'BTCUSDT-15m-{d.year}-{d.month:02}.zip'
        require(item['name'] == name and item['url'] == BASE + name
                and item['first_open_ms'] == start and item['bars'] == (end - start) // BAR_MS
                and w['timestamp_unit'] == 'MILLISECONDS', 'SOURCE_URI_GRID_OR_UNIT_DRIFT')
        for key in ('archive_sha256', 'checksum_sha256', 'member_sha256'):
            require(bool(re.fullmatch('[0-9a-f]{64}', item[key])), 'EXPLICIT_BYTE_PIN_REQUIRED')
        for key in ('archive_bytes', 'checksum_bytes'):
            require(type(item[key]) is int and 0 < item[key] <= MAX_BYTES, 'SOURCE_SIZE_PIN_REQUIRED')
        periods.append((start, end))
    periods.sort()
    require(all(periods[i][1] + plan['embargo_ms'] <= periods[i+1][0]
                for i in range(len(periods)-1)), 'NONCONTIGUOUS_WINDOWS_AND_72H_GAP_REQUIRED')
    return plan


def read_plan(path, expected_sha):
    raw = Path(path).read_bytes()
    require(sha(raw) == expected_sha, 'FROZEN_PLAN_SHA_MISMATCH')
    return validate_plan(parse(raw)), raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AccessDenied('HTTP_REDIRECT_DENIED')


def fetch_public(url):
    """Single bounded official archive GET, no proxy, redirect, auth or retry."""
    require(url.startswith(BASE) and bool(re.fullmatch(
        r'BTCUSDT-15m-202[34]-(0[1-9]|1[0-2])\.zip(?:\.CHECKSUM)?', url[len(BASE):])),
        'ONLY_OFFICIAL_PREDECLARED_PUBLIC_ARCHIVE_URI')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    started = iso_now()
    try:
        with opener.open(url, timeout=30) as response:
            require(response.status == 200, 'HTTP_STATUS_NOT_200')
            raw = response.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, 'FETCH_SIZE_LIMIT')
            return raw, {'url': url, 'started_at_utc': started, 'received_at_utc': iso_now(),
                         'status': response.status, 'sha256': sha(raw), 'bytes': len(raw),
                         'clock_custody': 'LOCAL_CLOCK_UNVERIFIED'}
    except urllib.error.HTTPError as exc:
        raise AccessDenied('HTTP_DENIED_' + str(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise AccessDenied('NETWORK_UNAVAILABLE_' + type(exc.reason).__name__) from exc
    except OSError as exc:
        raise AccessDenied('NETWORK_IO_FAILED_' + type(exc).__name__) from exc


def read_source(window, cache, *, fetch=False, fetcher=fetch_public):
    item = window['source']
    blobs, access = [], []
    for suffix, kind in (('', 'archive'), ('.CHECKSUM', 'checksum')):
        path = Path(cache) / (item['name'] + suffix)
        if path.exists():
            require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES,
                    'UNSAFE_OR_OVERSIZE_CACHE_FILE')
            raw = path.read_bytes()
            access.append({'url': item['url'] + suffix, 'mode': 'REUSED_LOCAL_ORIGINAL',
                           'current_http_request': False})
        else:
            require(fetch, 'SOURCE_NOT_AVAILABLE_AND_FETCH_NOT_ENABLED')
            raw, event = fetcher(item['url'] + suffix)
            access.append({'mode': 'PUBLIC_ARCHIVE_GET', **event})
        require(sha(raw) == item[kind + '_sha256'] and len(raw) == item[kind + '_bytes'],
                'SOURCE_BYTE_PIN_DRIFT_' + kind)
        blobs.append(raw)
    require(blobs[1].decode('ascii').split() == [item['archive_sha256'], item['name']],
            'VENDOR_CHECKSUM_MISMATCH')
    # Reuse strict original B1 parser ONLY: no B1 evaluation/runner invocation.
    try:
        rows, member = parse_archive(blobs[0], item['name'][:-4] + '.csv',
                                     item['first_open_ms'], item['bars'])
    except (ValueError, KeyError, ArithmeticError, zipfile.BadZipFile) as exc:
        raise IntakeError('NATIVE_ARCHIVE_REJECTED: ' + str(exc)) from exc
    require(sha(member) == item['member_sha256'], 'CSV_MEMBER_CORRECTION_DRIFT')
    bars = []
    for row in rows:
        bar = dict(schema=INDEX_SCHEMA, dataset_id=window['dataset_id'], dataset_version=1,
            bar_id='BINANCE:SPOT:BTCUSDT:15m:' + row[0], source_exchange='BINANCE',
            source_market='SPOT', symbol='BTCUSDT', interval_ms=BAR_MS,
            open_ms=int(row[0]), close_ms=int(row[6]),
            **{key: str(Decimal(row[i])) for key, i in [('open',1),('high',2),('low',3),('close',4),('volume',5)]},
            source_archive_sha256=item['archive_sha256'], source_member_sha256=item['member_sha256'],
            source_version='archive-sha256:' + item['archive_sha256'], correction_generation='UNKNOWN_NOT_ATTESTED',
            correction_parent=None, finality='ARCHIVED_CLOSED_INTERVAL', is_final=True,
            availability_mode='RETROSPECTIVE_NON_PIT', historical_known_at_ms=None,
            historical_receipt_ms=None, historical_publication_ms=None,
            observation_lower_bound_ms=int(row[6]) + 1)
        require(all(math.isfinite(float(bar[k])) for k in ['open','high','low','close','volume']),
                'UNSUPPORTED_NUMERIC_RANGE')
        bar['bar_sha256'] = sha(canonical(bar))
        bars.append(bar)
    return bars, blobs, access


def cached_fetch_evidence(window, receipt_bytes):
    """Retained acquisition record, not an authenticated publisher/arrival clock."""
    if receipt_bytes is None:
        return {'status': 'UNKNOWN_NO_RETAINED_FETCH_RECEIPT', 'reported_fetch_at_utc': None}
    receipts = parse(receipt_bytes)
    item = window['source']
    matches = [x for x in receipts if x.get('archive', {}).get('url') == item['url']]
    require(len(matches) == 1, 'CACHE_RECEIPT_MISSING_OR_DUPLICATE_SOURCE')
    r = matches[0]
    for kind, suffix in [('archive',''),('checksum','.CHECKSUM')]:
        require(r[kind]['url'] == item['url'] + suffix and r[kind]['sha256'] == item[kind+'_sha256']
                and r[kind]['bytes'] == item[kind+'_bytes'] and r[kind]['http_status'] == 200,
                'CACHE_RECEIPT_SOURCE_PIN_DRIFT')
    utc_ms(r['observed_at_utc'].replace('+00:00', 'Z'))
    return {'status': 'RETAINED_LOCAL_FETCH_RECORD_PIN_MATCH_NOT_INDEPENDENT_ATTESTATION',
            'reported_fetch_at_utc': r['observed_at_utc'], 'receipt_file_sha256': sha(receipt_bytes),
            'historical_publication_ms': None, 'historical_known_at_ms': None}


def inspect_window(window, bars):
    closes = [float(b['close']) for b in bars]
    returns = [math.log(closes[i] / closes[i-1]) for i in range(1,len(closes))]
    return {'dataset_id': window['dataset_id'], 'start_utc': window['start_utc'],
        'end_exclusive_utc': window['end_exclusive_utc'], 'expected_bars': window['source']['bars'],
        'observed_bars': len(bars), 'gap_count': 0, 'duplicate_count': 0,
        'quality': 'COMPLETE_ARCHIVED_NATIVE_GRID', 'regime_label': None,
        'regime_evidence': 'NOT_CLASSIFIED_NO_CORE_PROOF',
        'market_context_only': {'close_log_return_std_15m': statistics.pstdev(returns),
            'month_close_over_first_open_minus_1': closes[-1] / float(bars[0]['open']) - 1,
            'high_low_over_first_open': (max(float(b['high']) for b in bars) -
                                       min(float(b['low']) for b in bars)) / float(bars[0]['open'])},
        'statistical_strategy_evaluation': False}


def intake(plan, plan_raw, cache, *, verified_at_utc, fetch=False,
           receipt_bytes=None, fetcher=fetch_public, code_sha=None):
    validate_plan(plan)
    require(parse(plan_raw) == plan, 'PLAN_OBJECT_BYTES_DRIFT')
    require(code_sha is None or bool(re.fullmatch('[0-9a-f]{40}', code_sha)), 'CODE_SHA_FORMAT')
    require(utc_ms(verified_at_utc) >= utc_ms(plan['declared_at_utc']), 'INTAKE_PRECEDES_DECLARATION')
    index, coverage, raw_files, access = [], [], {}, []
    for w in plan['development_windows']:
        try:
            bars, blobs, events = read_source(w, cache, fetch=fetch, fetcher=fetcher)
            evidence = cached_fetch_evidence(w, receipt_bytes) if all(
                e['mode'] == 'REUSED_LOCAL_ORIGINAL' for e in events) else {
                    'status': 'CURRENT_PUBLIC_FETCH', 'reported_fetch_at_utc': None}
            index.extend(bars)
            coverage.append({**inspect_window(w, bars), 'source': w['source'],
                             'acquisition_evidence': evidence, 'verified_at_utc': verified_at_utc})
            access.extend(events)
            for suffix, blob in zip(('', '.CHECKSUM'), blobs):
                raw_files[w['source']['name'] + suffix] = blob
        except (IntakeError, FileNotFoundError, OSError) as exc:
            coverage.append({'dataset_id': w['dataset_id'], 'quality': 'BLOCKED_SOURCE',
                             'expected_bars': w['source']['bars'], 'observed_bars': None,
                             'gap_count': None, 'reason': str(exc)})
            if isinstance(exc, AccessDenied):
                break  # denied/failed egress is terminal: no alternate/retry/proxy.
    completed = len(coverage) == len(plan['development_windows']) and all(
        w['quality'] == 'COMPLETE_ARCHIVED_NATIVE_GRID' for w in coverage)
    index_raw = b''.join(canonical(b) for b in index)
    manifest = {'schema': 'aql.p2a-data-intake-manifest.v1', 'phase': 'DEVELOPMENT_ONLY',
        'code_sha': code_sha, 'parser_dependency_sha': '47558bea22af5480aa84148fd22bf2890bbe22ae',
        'status': 'COMPLETE_DEVELOPMENT_INTAKE' if completed else 'BLOCKED_OR_PARTIAL_INTAKE',
        'plan_sha256': sha(plan_raw), 'bar_index_schema': INDEX_SCHEMA,
        'bar_index_sha256': sha(index_raw), 'validated_bars': len(index),
        'development_windows': coverage, 'attempted_windows': len(coverage),
        'unattempted_windows': len(plan['development_windows']) - len(coverage),
        'verified_at_utc': verified_at_utc, 'source_access_events': access,
        'availability_mode': 'RETROSPECTIVE_NON_PIT', 'source_finality_scope': 'ARCHIVED_CLOSED_INTERVAL_NOT_LIVE_FINALITY_RECEIPT',
        'correction_history': 'UNKNOWN_NOT_ATTESTED_NEW_BYTES_REQUIRE_NEW_PLAN_VERSION',
        'historical_known_at_ms': None, 'historical_publication_ms': None,
        'terms': plan['terms'], 'sealed_holdout': plan['sealed_holdout'], 'embargo_ms': plan['embargo_ms'],
        'holdout_fetched': False, 'holdout_evaluated': False,
        'core_opportunity_producer': 'NOT_INVOKED_SEPARATE_CORE_CONTRACT',
        'paired_lab_consumer': 'NOT_INVOKED_SEPARATE_FACTORY_CONSUMER',
        'base_shadow_comparison': 'NOT_EXECUTED_NO_FROZEN_BASE_SHADOW_PROOF',
        'opportunities': None, 'comparative_alpha': None, 'market_only_opportunity_probe': 'NOT_RUN',
        'no_trading': True, 'g0_approval': False}
    return manifest, index_raw, raw_files


def read_validated_index(directory, *, expected_manifest_sha256):
    root = Path(directory)
    raw = (root / 'intake-manifest.json').read_bytes()
    require(sha(raw) == expected_manifest_sha256, 'MANIFEST_TRANSPORT_DRIFT')
    m = parse(raw)
    require(m['status'] == 'COMPLETE_DEVELOPMENT_INTAKE' and m['phase'] == 'DEVELOPMENT_ONLY',
            'INCOMPLETE_OR_NON_DEVELOPMENT_HANDOFF')
    plan_raw = (root / 'frozen-plan.json').read_bytes()
    require(sha(plan_raw) == m['plan_sha256'], 'FROZEN_PLAN_TRANSPORT_DRIFT')
    plan = validate_plan(parse(plan_raw))
    index = (root / 'bars.jsonl').read_bytes()
    require(sha(index) == m['bar_index_sha256'], 'BAR_INDEX_TRANSPORT_DRIFT')
    rows = [parse(line) for line in index.splitlines() if line.strip()]
    require(len(rows) == m['validated_bars'], 'BAR_INDEX_DENOMINATOR')
    for row in rows:
        require(row['bar_sha256'] == sha(canonical({k:v for k,v in row.items() if k!='bar_sha256'})),
                'BAR_RECORD_DRIFT')
    return plan, m, rows


def asof_features(rows, plan, *, dataset_id, cutoff_ms):
    """Only from read_validated_index; retrospective event-time prefix, NOT PIT."""
    matches = [w for w in plan['development_windows'] if w['dataset_id'] == dataset_id]
    require(len(matches) == 1, 'UNKNOWN_OR_SEALED_DATASET')
    w = matches[0]
    start, end = utc_ms(w['start_utc']), utc_ms(w['end_exclusive_utc'])
    guard_development(start, end, plan)
    require(type(cutoff_ms) is int and start <= cutoff_ms <= end and cutoff_ms % BAR_MS == 0,
            'CUTOFF_OUTSIDE_DECLARED_DEVELOPMENT_GRID')
    return tuple(r for r in rows if r['dataset_id'] == dataset_id and r['close_ms'] < cutoff_ms)


def core_source_handoff(manifest, index_raw):
    """Constructor arguments for Core #221 source types only, NOT opportunities.

    Core pin 9823f68221cc31e4b12dc11d5713513df22c69fb; no cross-branch import.
    """
    rows = [parse(line) for line in index_raw.splitlines() if line.strip()]
    sources = []
    if manifest['status'] == 'COMPLETE_DEVELOPMENT_INTAKE':
        for window in manifest['development_windows']:
            selected = [r for r in rows if r['dataset_id'] == window['dataset_id']]
            sources.append({'source_kwargs': {
                'source_id': window['dataset_id'], 'exchange': 'BINANCE', 'market': 'SPOT', 'symbol': 'BTCUSDT',
                'source_package_sha256': window['source']['archive_sha256'],
                'manifest_sha256': sha(canonical(manifest)),
                'normalized_sha256': sha(b''.join(canonical(r) for r in selected)),
                'correction_generation': 'UNKNOWN_NOT_ATTESTED', 'interval_ms': BAR_MS,
                'evidence_class': 'RETROSPECTIVE_NON_PIT'},
                'normalized_hash_domain': 'CANONICAL_JSONL_OF_THIS_DATASET_WORK_BAR_RECORDS',
                'bar_kwargs': [{'open_ms': r['open_ms'], 'close_ms': r['close_ms'],
                    'content_sha256': r['bar_sha256'], 'finalized': r['is_final'],
                    'available_at_ms': None, 'availability_evidence_ref': None} for r in selected]})
    return {'schema': 'aql.p2a.core-source-constructor-handoff.v1',
            'core_contract_sha': '9823f68221cc31e4b12dc11d5713513df22c69fb',
            'status': 'SOURCE_ARGUMENTS_ONLY_NO_CORE_SCHEDULE_EXECUTED', 'sources': sources,
            'opportunities': None, 'frozen_trial': None, 'comparison_executed': False}


def persist(out, manifest, index_raw, raw_files, plan_raw):
    target = Path(out)
    require(not target.exists(), 'IMMUTABLE_OUTPUT_ALREADY_EXISTS')
    files = {'frozen-plan.json': plan_raw, 'intake-manifest.json': canonical(manifest),
             'core-source-handoff.json': canonical(core_source_handoff(manifest, index_raw)),
             'bars.jsonl': index_raw, **{'raw/' + n: b for n, b in raw_files.items()}}
    files['coverage.md'] = ('# P2-A development data intake only\n\nAttribution: Binance Vision. '
        'CC BY-NC-SA4.0, personal noncommercial nonproduction research.\n\n'
        + json.dumps({'status':manifest['status'], 'windows':manifest['development_windows']},
                     sort_keys=True, indent=2)
        + '\n\nNo P2 strategy comparison/alpha, no PIT. Sealed holdout not fetched/evaluated.\n').encode()
    files['sha256-manifest.json'] = canonical({n: sha(b) for n,b in sorted(files.items())})
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.p2a-') as temp:
        for n, b in files.items():
            p = Path(temp) / n
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('xb') as f:
                os.chmod(p, 0o600)
                f.write(b); f.flush(); os.fsync(f.fileno())
        target.mkdir(mode=0o700)
        for p in Path(temp).iterdir():
            os.rename(p, target / p.name)
    return sha(files['intake-manifest.json'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--cache-receipt', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--verified-at-utc', required=True)
    p.add_argument('--code-sha', required=True)
    p.add_argument('--fetch', action='store_true', help='Only missing pinned DEVELOPMENT archives; no holdout')
    a = p.parse_args()
    plan, raw = read_plan(a.plan, a.plan_sha256)
    manifest, index, originals = intake(plan, raw, a.cache, verified_at_utc=a.verified_at_utc,
        receipt_bytes=a.cache_receipt.read_bytes() if a.cache_receipt else None, fetch=a.fetch, code_sha=a.code_sha)
    digest = persist(a.output, manifest, index, originals, raw)
    print(json.dumps({'status': manifest['status'], 'validated_bars':manifest['validated_bars'],
                      'intake_manifest_sha256': digest, 'bar_index_sha256':sha(index),
                      'holdout_fetched':False, 'comparison':manifest['base_shadow_comparison']}, sort_keys=True))
    if manifest['status'] != 'COMPLETE_DEVELOPMENT_INTAKE':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
