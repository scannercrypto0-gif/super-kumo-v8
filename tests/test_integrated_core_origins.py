"""Final-tree import seam: accepted main Core is not the frozen research kernel.

These are integration-origin regressions, not a repeated audit of D12a/D18.
The #296 dependency manifest remains immutable; a loaded old implementation is
never described as patched merely because main's copy passed accepted tests.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_336 = "1d1dfe913455d043c4269891e2e713b1e57ffc97"
ACCEPTED_MAIN_BYTES = {
    "research_wp_r0/attempt_ledger.py": "cfecbe1ba2ae7aabf81430fd3a9ab786606a081aef815a4eea0030a15983d767",
    "research_wp_r0/historical_library.py": "7757efa6722e1ca0dc842897f520315d6644538289c0699429d0b8643241fc69",
}


def _subprocess(code, *arguments):
    process = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT), *map(str, arguments)],
        cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=90)
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout.strip().splitlines()[-1])


def test_collected_main_core_interfaces_resolve_exact_accepted_336_bytes():
    # Check the actual pytest interpreter after every module has been collected,
    # catching dependency sys.path pollution that subprocess-only probes miss.
    import research_wp_r0.attempt_ledger as ledger
    import research_wp_r0.historical_library as history
    for relative, module in zip(ACCEPTED_MAIN_BYTES, (ledger, history)):
        assert Path(module.__file__).resolve() == (ROOT / relative).resolve()
        assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == ACCEPTED_MAIN_BYTES[relative]


def test_main_core_interfaces_resolve_exact_accepted_336_bytes():
    result = _subprocess(r'''
import hashlib,inspect,json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import research_wp_r0.attempt_ledger as ledger
import research_wp_r0.historical_library as history
print(json.dumps({name:{'path':str(Path(inspect.getfile(module)).resolve()),
 'sha256':hashlib.sha256(Path(inspect.getfile(module)).read_bytes()).hexdigest()}
 for name,module in [('research_wp_r0/attempt_ledger.py',ledger),('research_wp_r0/historical_library.py',history)]}))
''')
    for relative, expected_hash in ACCEPTED_MAIN_BYTES.items():
        assert result[relative]["path"] == str((ROOT / relative).resolve())
        assert result[relative]["sha256"] == expected_hash


def test_actual_analyzer_loads_frozen_origins_without_silent_336_overlay():
    result = _subprocess(r'''
import hashlib,importlib.util,inspect,json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
from tools.realtime_market_feed import forward_research as fr
base=root/'.integration/research-baseline';deps=root/'.integration/research-kernel'
kernel=fr._load_kernel(base,deps)
import research_wp_r0.historical_library as history
plan=kernel['plan'];manifest={x['path']:x['sha256'] for x in plan['dependency_files']}
path=Path(inspect.getfile(history)).resolve()
ledger_spec=importlib.util.find_spec('research_wp_r0.attempt_ledger')
print(json.dumps({'history_path':str(path),'history_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
 'history_manifest_sha256':manifest['factory/research_wp_r0/historical_library.py'],
 'attempt_ledger_was_loaded':'research_wp_r0.attempt_ledger' in sys.modules,
 'attempt_ledger_resolves_to':str(Path(ledger_spec.origin).resolve()),
 'attempt_manifest_sha256':manifest['factory/research_wp_r0/attempt_ledger.py'],
 'strategy_definition_sha256':kernel['definition'].digest,
 'scanner_evaluator_path':str(Path(inspect.getfile(kernel['evaluate'])).resolve())}))
''')
    deps = ROOT / ".integration/research-kernel"
    assert result["history_path"] == str((deps / "factory/research_wp_r0/historical_library.py").resolve())
    assert result["history_sha256"] == result["history_manifest_sha256"]
    assert result["history_sha256"] != ACCEPTED_MAIN_BYTES["research_wp_r0/historical_library.py"]
    assert result["attempt_ledger_resolves_to"] == str((deps / "factory/research_wp_r0/attempt_ledger.py").resolve())
    assert result["attempt_manifest_sha256"] != ACCEPTED_MAIN_BYTES["research_wp_r0/attempt_ledger.py"]
    assert result["scanner_evaluator_path"] == str((deps / "scanner/tools/scanner_strategy_f/research_e2e_diagnostic.py").resolve())
    assert result["strategy_definition_sha256"] == "bab9bac7e8cbb6dca5db21ba685a5027d2f197babbc2ec7c60468233a724aabf"


def test_native_forward_chain_does_not_invoke_frozen_custody_or_attempt_admission(tmp_path):
    # The source is still the real generated native-feed fixture. Only unused
    # frozen interfaces are armed to refuse; consumer APIs are not mocked.
    from tools.realtime_market_feed.test_native_consumers import args_for
    arguments = args_for(tmp_path)
    request = tmp_path / "origin-arguments.json"
    request.write_text(json.dumps(arguments))
    result = _subprocess(r'''
import hashlib,inspect,json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root),str(root/'.integration/warehouse/src')]
from tools.realtime_market_feed import native_consumers as native
from tools.realtime_market_feed import forward_research as fr
args=json.loads(Path(sys.argv[2]).read_text())
fr._load_kernel(args['baseline_root'],args['dependency_root'])
import research_wp_r0.historical_library as history
import research_wp_r0.attempt_ledger as attempt
calls=[]
def forbid(*a,**kw):
 calls.append('FROZEN_CUSTODY_OR_ADMISSION_CALLED')
 raise AssertionError(calls[-1])
history.HistoricalBar.__post_init__=forbid
history.HistoricalLibrary.register=forbid
history.HistoricalLibrary.snapshot=forbid
attempt.AttemptLedger.__init__=forbid
source=Path(args.pop('feed_database'));before=hashlib.sha256(source.read_bytes()).hexdigest()
projected=args.pop('research_database')
value=native.run_generated_native_chain(source,projected,**args)
print(json.dumps({'calls':calls,'source_unchanged':before==hashlib.sha256(source.read_bytes()).hexdigest(),
 'census':value['native_consumers']['census'],
 'secretary':value['native_consumers']['secretary']['state'],
 'source_class':value['receipt']['source']['source_class'],
 'history_origin':str(Path(inspect.getfile(history)).resolve()),
 'attempt_origin':str(Path(inspect.getfile(attempt)).resolve()),
 'orders':value['native_consumers']['orders'],'trading_authority':value['native_consumers']['trading_authority']}))
''', request)
    assert result["calls"] == []
    assert result["source_unchanged"]
    assert result["census"]["decision_slots"] == 12
    assert result["census"]["signal_unknown"] == 7
    assert result["secretary"] == "WAIT_AUTHENTICATED_PARENTS_AND_RESEARCH_REVIEW"
    assert result["source_class"] == "FORWARD_UNQUALIFIED"
    assert result["orders"] == 0 and result["trading_authority"] == "NONE"
