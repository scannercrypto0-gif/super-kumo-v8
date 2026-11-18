"""B1 original Binance archive replay. Market description only; no strategy or PIT.

No signal reconstruction, fill inference, external witness callbacks or engine calls.
The committed acquisition lock is a local byte commitment, not issuer attestation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

BAR_MS = 900000
FIELDS = ('open_ms', 'open', 'high', 'low', 'close', 'volume', 'close_ms',
          'quote_volume', 'trades', 'taker_base', 'taker_quote', 'ignore')
BASE = 'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode()


def parse_archive(data, member, first_ms, count):
    """Reject changed member, duplicate/gap/grid, malformed OHLCV and nonfinite data."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if z.namelist() != [member] or z.infolist()[0].file_size > 32*1024*1024:
            raise ValueError('ZIP member identity/size')
        raw = z.read(member)  # includes ZIP CRC validation; never extract paths
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8'))))
    if len(rows) != count:
        raise ValueError('bar count')
    for i, row in enumerate(rows):
        if len(row) != 12:
            raise ValueError('12-column schema')
        if not all(re.fullmatch(r'[0-9]+', row[j]) for j in (0, 6, 8)):
            raise ValueError('integer schema')
        if int(row[0]) != first_ms+i*BAR_MS or int(row[6]) != int(row[0])+BAR_MS-1:
            raise ValueError('15m contiguous millisecond grid')
        o,h,l,c,v,q,tb,tq,ignored = [Decimal(row[j]) for j in (1,2,3,4,5,7,9,10,11)]
        if not all(x.is_finite() for x in (o,h,l,c,v,q,tb,tq,ignored)):
            raise ValueError('nonfinite price/volume')
        if not (0 < l <= min(o,c) <= max(o,c) <= h):
            raise ValueError('OHLC ordering')
        if min(v,q,tb,tq,ignored) < 0 or tb > v or tq > q:
            raise ValueError('volume ordering')
    return rows, raw


def load_originals(lock, data_dir, download=False):
    if lock['schema'] != 'aql.b1.original-market-lock.v1' or len(lock['archives']) != 12:
        raise ValueError('fixed 2024 twelve-month lock required')
    rows, inventory, observations = [], [], []
    for month, item in enumerate(lock['archives'], 1):
        name = f'BTCUSDT-15m-2024-{month:02}.zip'
        first = int(datetime(2024,month,1,tzinfo=timezone.utc).timestamp()*1000)
        end = int(datetime(2025 if month == 12 else 2024,
                           1 if month == 12 else month+1,1,tzinfo=timezone.utc).timestamp()*1000)
        if (item['name'] != name or item['url'] != BASE+name or
                item['first_open_ms'] != first or item['bars'] != (end-first)//BAR_MS):
            raise ValueError('lock source/period drift')
        contents = []
        for suffix, key in (('', 'archive'), ('.CHECKSUM', 'checksum')):
            path = data_dir/(name+suffix)
            if not path.exists() and download:
                with urllib.request.urlopen(BASE+name+suffix, timeout=60) as response:
                    blob = response.read(32*1024*1024+1)
                    if len(blob) > 32*1024*1024:
                        raise ValueError('download size limit')
                    observations.append({'url':BASE+name+suffix,'status':response.status,
                                         'observed_at_utc':datetime.now(timezone.utc).isoformat(),
                                         'headers':dict(response.headers)})
                path.write_bytes(blob)
            blob = path.read_bytes()
            if sha(blob) != item[key+'_sha256'] or len(blob) != item[key+'_bytes']:
                raise ValueError('locked original '+key+' changed: '+name)
            contents.append(blob)
        checksum = contents[1].decode('ascii').strip().split()
        if checksum != [item['archive_sha256'], name]:
            raise ValueError('same-publisher checksum mismatch')
        parsed, member_raw = parse_archive(contents[0], name[:-4]+'.csv', first, item['bars'])
        if sha(member_raw) != item['member_sha256']:
            raise ValueError('CSV member hash changed')
        rows.extend(parsed)
        inventory.append({**item, 'observed_bars':len(parsed),
                          'integrity_status':'LOCK_AND_VENDOR_CHECKSUM_AND_GRID_MATCH'})
    start = int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp()*1000)
    if len(rows) != 35136 or any(int(r[0]) != start+i*BAR_MS for i,r in enumerate(rows)):
        raise ValueError('year coverage gap/duplicate')
    return rows, inventory, observations


def describe_market(rows, windows_path):
    """Every closed bar is a descriptive anchor, never a strategy opportunity.

    Reference is next bar OPEN, horizon endpoint is that future window's last
    CLOSE. Anchors without a complete future horizon remain CENSORED. Gross
    unsigned range and signed raw price changes are not directional F1 MFE/MAE.
    """
    summaries = []
    with windows_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['anchor_close_ms','horizon_hours','status','next_open',
                         'endpoint_close','gross_price_change_bps','unsigned_high_low_range_bps'])
        for hours in (4,24,72):
            steps = hours*4
            changes, ranges = [], []
            for i, row in enumerate(rows):
                if i+steps >= len(rows):
                    writer.writerow([row[6],hours,'CENSORED','','','',''])
                    continue
                future = rows[i+1:i+steps+1]
                ref = Decimal(future[0][1])
                change = (Decimal(future[-1][4])/ref-1)*10000
                width = (max(Decimal(r[2]) for r in future)-min(Decimal(r[3]) for r in future))/ref*10000
                changes.append(change); ranges.append(width)
                writer.writerow([row[6],hours,'COMPLETE',str(ref),future[-1][4],
                                 format(change,'.8f'),format(width,'.8f')])
            def mean(values):
                return format(sum(values)/len(values),'.8f') if values else None
            summaries.append({'horizon_hours':hours,'market_anchor_denominator':len(rows),
                              'complete':len(changes),'censored':len(rows)-len(changes),
                              'positive_gross_price_change':sum(x>0 for x in changes),
                              'negative_gross_price_change':sum(x<0 for x in changes),
                              'zero_gross_price_change':sum(x==0 for x in changes),
                              'mean_gross_price_change_bps':mean(changes),
                              'mean_unsigned_high_low_range_bps':mean(ranges)})
    return summaries


def replay(lock_path, data_dir, out, download=False):
    # Evidence outputs are new; never silently overwrite an earlier result.
    out.mkdir(parents=True, exist_ok=False)
    lock_bytes = lock_path.read_bytes()
    rows, inventory, observations = load_originals(json.loads(lock_bytes),data_dir,download)
    normalized = b''.join(canonical(dict(zip(FIELDS,r))) for r in rows)
    (out/'normalized15m.jsonl').write_bytes(normalized)
    windows = out/'market-windows.csv'
    horizons = describe_market(rows, windows)
    first, last = Decimal(rows[0][1]),Decimal(rows[-1][4])
    report = {'schema':'aql.b1.market-only-report.v1',
              'project_id':'AQL-CRYPTO-RESEARCH-001','scope':'RETROSPECTIVE_MARKET_ONLY',
              'source':'Binance Vision Spot BTCUSDT 15m',
              'period_start_utc':'2024-01-01T00:00:00Z',
              'period_end_exclusive_utc':'2025-01-01T00:00:00Z',
              'expected_bars':35136,'observed_bars':len(rows),'missing_bars':0,'duplicate_bars':0,
              'lock_sha256':sha(lock_bytes),'originals':inventory,
              'normalization':'12 source text fields, named canonical ASCII sorted JSONL; no resampling/imputation',
              'normalized_sha256':sha(normalized),'market_windows_sha256':sha(windows.read_bytes()),
              'horizons':horizons,
              'passive_price_context':{'first_open':str(first),'last_close':str(last),
                  'gross_price_change_bps':format((last/first-1)*10000,'.8f'),
                  'is_strategy_baseline_comparison':False},
              'strategy_join':{'status':'BLOCKED_ORIGINAL_CORE_SIGNALS_NOT_SUPPLIED',
                  'scheduled_opportunities':None,'arm_denominator_2N':None,'horizon_denominator_6N':None,
                  'wins':None,'losses':None,'unknown':None,'target_stop_ordering':None,
                  'indicator_outcome_association':None,'paired_baseline_comparison':None,
                  'reason':'Unknown N is not zero; controlled Core sample is not historical original'},
              'costs':{'applied_to_market_statistics':False,
                  'execution_fee_slippage_spread':'NOT_CONFIGURED_NO_EXECUTION_OR_PNL',
                  'illustrative_roundtrip_bps':32,
                  'illustrative_only':'full spread 2 + slippage 2*5 + fee 2*10; not measured or approved for run'},
              'correction_history':'UNKNOWN_CURRENT_DOWNLOAD_SNAPSHOT_ONLY',
              'independent_issuer_clock_custody_preF3_anchor':'BLOCKED_EXTERNAL_EVIDENCE',
              'realized_fills_or_pnl':False,'operational_pit_proven':False,
              'g0_or_deployment_authorized':False,
              'limitations':['Overlapping horizons are dependent; no significance or profitability inference',
                  '2024 was chosen for fixed full-year coverage before inspecting results, not preregistered OOS',
                  'Same-publisher checksum/HTTP last-modified is not independent historical availability/correction proof',
                  'Local immutable-by-hash lock is not independently protected external custody',
                  'No authenticated strategy direction/levels/monitoring snapshots were supplied']}
    (out/'report.json').write_bytes(canonical(report))
    (out/'retrieval-observations.json').write_bytes(canonical(observations))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lock',type=Path,required=True)
    p.add_argument('--data-dir',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--download',action='store_true')
    args=p.parse_args(); args.data_dir.mkdir(parents=True,exist_ok=True)
    result=replay(args.lock,args.data_dir,args.out,args.download)
    print(json.dumps({k:result[k] for k in ('scope','observed_bars','horizons','strategy_join')},indent=2))


if __name__ == '__main__':
    main()
