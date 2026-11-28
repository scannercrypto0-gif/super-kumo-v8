"""Opt-in finite snapshot/manifest refresh from explicit sanitized report paths.

No source worker, scheduler, listener, network, directory search or live DB read.
A manifest is the publication commit point; failed cycles never replace prior
snapshots/manifests. Host activation and two original cycles remain separate.
"""
import argparse
import json
import os
import re
from pathlib import Path
import tempfile
import time

import atlas_early_observation as early
import atlas_ops_watchdog as watchdog


def atomic_new(path, value):
    raw = watchdog.canonical(value)
    early.require(len(raw) <= early.MAX_FILE_BYTES, 'REFRESH_OUTPUT_BOUND')
    target = Path(path)
    early.require(not target.exists() and not target.is_symlink(), 'REFRESH_CREATE_ONLY')
    fd, name = tempfile.mkstemp(prefix='.refresh-pending-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.link(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    return watchdog.digest(raw)


def select_latest(root, prefix):
    """Bounded direct-child name inventory in an explicitly approved report root.

    Does not read candidate payloads, recurse or search alternate roots. Invalid
    newest payload is selected and refused by the consumer, never skipped.
    """
    early.require(type(prefix) is str and re.fullmatch(r"(?:history-[a-f0-9]{16}|daily-[a-f0-9]{16}|realtime-[a-f0-9]{32})-", prefix)
                  and ".." not in prefix, 'REFRESH_SELECTOR_PREFIX')
    best = None
    seen = 0
    with os.scandir(root) as entries:
        for entry in entries:
            seen += 1
            early.require(seen <= 512, 'REFRESH_SELECTOR_ENTRY_BOUND')
            match = re.fullmatch(re.escape(prefix) + r"([0-9]{1,16})\.json", entry.name)
            if match:
                sequence = int(match[1])
                early.require(sequence <= 10**15, "REFRESH_SELECTOR_SEQUENCE_BOUND")
                early.require(best is None or sequence != best[0], 'REFRESH_SELECTOR_SEQUENCE_CONFLICT')
                if best is None or sequence > best[0]:
                    best = (sequence, entry.name)
    return root/best[1] if best else None


def refresh_once(paths, *, approved_input_root, approved_output_root, sequence,
                 now_ms, monotonic_ns, boot_id, clock_uncertainty_ms=None,
                 producer_pins=None, previous_name=None, producer_selectors=None):
    started_ns=time.perf_counter_ns();cpu_started_ns=time.process_time_ns()
    root = early.checked_root(approved_input_root, 'APPROVED_INPUT_ROOT_REQUIRED')
    output = early.checked_root(approved_output_root, 'APPROVED_OUTPUT_ROOT_REQUIRED')
    early.require(root != output and root not in output.parents and output not in root.parents,
                  'APPROVED_ROOTS_MUST_BE_SEPARATE')
    early.require(type(sequence) is int and 0 <= sequence < 10**12, 'REFRESH_SEQUENCE')
    explicit = {k: early.require_direct_child(p, root, 'INPUT_OUTSIDE_APPROVED_ROOT')
                if p is not None else None for k, p in paths.items()
                if k in {'history','registry','daily','daily_source','live'}}
    pins = {k: dict(v) for k, v in (producer_pins or {}).items()}
    for lane, prefix in (producer_selectors or {}).items():
        early.require(lane in {'history','daily_source','live'} and not explicit.get(lane),
                      'REFRESH_SELECTOR_SCOPE')
        expected_prefix = {"history": "history-", "daily_source": "daily-", "live": "realtime-"}[lane]
        early.require(prefix.startswith(expected_prefix), "REFRESH_SELECTOR_LANE")
        explicit[lane] = select_latest(root, prefix)
        identity = prefix[len(expected_prefix):-1]
        key = "daily" if lane == "daily_source" else lane
        pins.setdefault(key, {})["run_id" if lane == "live" else "producer_identity"] = identity
    if previous_name is not None:
        early.require(Path(previous_name).name == previous_name, 'PREVIOUS_OUTSIDE_APPROVED_OUTPUT_ROOT')
        explicit['previous'] = early.require_direct_child(output/previous_name, output, 'PREVIOUS_OUTSIDE_APPROVED_OUTPUT_ROOT')
    snapshot = early.build(explicit, now_ms=now_ms, monotonic_ns=monotonic_ns,
        boot_id=boot_id, clock_uncertainty_ms=clock_uncertainty_ms, producer_pins=pins,
        started_ns=started_ns,cpu_started_ns=cpu_started_ns)
    snap_path = early.require_direct_child(output/f'early-{sequence:012d}.json', output, 'OUTPUT_OUTSIDE_APPROVED_ROOT')
    manifest_path = early.require_direct_child(output/f'early-{sequence:012d}.manifest.json', output, 'OUTPUT_OUTSIDE_APPROVED_ROOT')
    # Refuse conflicts before any output. A later failure leaves at most an
    # unreferenced snapshot; no incomplete manifest becomes a reader authority.
    early.require(not snap_path.exists() and not manifest_path.exists(), 'REFRESH_CREATE_ONLY')
    snap_pin = atomic_new(snap_path, snapshot)
    body = dict(schema='atlas.mcp.early-source-manifest.v1', snapshot_path=str(snap_path.absolute()),
                snapshot_file_sha256=snap_pin)
    manifest = dict(body, manifest_sha256=watchdog.digest(watchdog.canonical(body)))
    manifest_pin = atomic_new(manifest_path, manifest)
    return dict(status='REFRESH_PUBLISHED_REPORT_ONLY', snapshot_name=snap_path.name,
        snapshot_sha256=snap_pin, manifest_name=manifest_path.name, manifest_sha256=manifest_pin,
        state=snapshot['state'], measurements=snapshot['measurements'], sequence=sequence,
        host_cycles_attested=False, network_calls=0, source_mutations=0, trading_authority='NONE')


def run_refresh(paths, *, cycles, interval_seconds, first_sequence=0, previous_name=None,
                now=lambda: time.time_ns()//1_000_000, monotonic=time.monotonic_ns,
                wait=time.sleep, **kwargs):
    early.require(type(cycles) is int and 1 <= cycles <= 2, 'REFRESH_CYCLE_BOUND')
    early.require(type(interval_seconds) is int and 300 <= interval_seconds <= 1800, 'REFRESH_INTERVAL_BOUND')
    results=[]
    for index in range(cycles):
        if index:wait(interval_seconds)
        result=refresh_once(paths, sequence=first_sequence+index, previous_name=previous_name,
            now_ms=now(), monotonic_ns=monotonic(), **kwargs)
        results.append(result); previous_name=result['snapshot_name']
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('history','registry','daily','daily_source','live'):
        parser.add_argument('--'+name.replace('_','-'),type=Path)
    parser.add_argument('--approved-input-root',type=Path,required=True)
    parser.add_argument('--approved-output-root',type=Path,required=True)
    parser.add_argument('--previous-name')
    for lane in ('history','daily_source','live'):
        parser.add_argument('--'+lane.replace('_','-')+'-producer-prefix')
    parser.add_argument('--cycles',type=int,choices=(1,2),default=1)
    parser.add_argument('--interval-seconds',type=int,default=300)
    parser.add_argument('--first-sequence',type=int,required=True)
    parser.add_argument('--clock-uncertainty-ms',type=int)
    for name in ('history_code_sha256','history_config_sha256','daily_source_code_sha256','daily_source_config_sha256','live_code_sha256','live_config_sha256'):
        parser.add_argument('--'+name.replace('_','-'))
    a=parser.parse_args()
    paths={k:getattr(a,k) for k in ('history','registry','daily','daily_source','live')}
    selectors={k:getattr(a,k+'_producer_prefix') for k in ('history','daily_source','live')
               if getattr(a,k+'_producer_prefix') is not None}
    pins={'history':{'code_sha256':a.history_code_sha256,'config_sha256':a.history_config_sha256},
          'daily':{'code_sha256':a.daily_source_code_sha256,'config_sha256':a.daily_source_config_sha256},
          'live':{'code_sha256':a.live_code_sha256,'config_sha256':a.live_config_sha256}}
    for result in run_refresh(paths,cycles=a.cycles, interval_seconds=a.interval_seconds,
            first_sequence=a.first_sequence, previous_name=a.previous_name,
            approved_input_root=a.approved_input_root,approved_output_root=a.approved_output_root,
            clock_uncertainty_ms=a.clock_uncertainty_ms,boot_id=watchdog.host_boot_id(),producer_pins=pins,producer_selectors=selectors):
        print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()
