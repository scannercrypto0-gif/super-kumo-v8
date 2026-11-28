"""Offline acceptance of the actual combined checkout; never opens host data.

Dependency setup is pinned Git code only. Pytest generates its own fixtures in
Python's system temporary directory; no guard is weakened by redirecting it.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    'research-baseline': 'eb49308d61ffdfc24ed5032df2cb541f37c48bfe',
    'warehouse': 'ae60b3e367241fec14753ac78e08147603b7af84',
    'watchdog': '8c7f37287cc6b0f4514a5604b56c6a24b26b5b63',
}
GROUPS = {
 'warehouse': ['tests/test_warehouse.py','tests/test_warehouse_september.py',
    'tests/test_september_correction.py','tests/test_full_history.py',
    'tests/test_resilient_history.py','tests/test_warehouse_registry.py',
    'tests/test_daily_warehouse_watchdog_seam.py','tests/test_warehouse_producer_report.py',
    'tests/test_research_timeframes.py','tests/test_research_forward_core_read.py',
    'tests/test_research_forward_scanner_boundary.py'],
 'realtime': ['tools/realtime_market_feed/test_service.py','tools/realtime_market_feed/test_backfill.py',
    'tools/realtime_market_feed/test_atlas_integration.py','tools/realtime_market_feed/test_acceptance_gates.py',
    'tools/realtime_market_feed/test_forward_research.py','tools/realtime_market_feed/test_cdr_d11b_evidence_class.py',
    'tools/realtime_market_feed/test_cdr_d14_evidence.py'],
 'mcp': ['tests/test_atlas_daily_health_evidence.py','tests/test_atlas_ops_watchdog.py',
    'tests/test_atlas_ops_mcp_pilot.py','tests/test_atlas_ops_mcp_freshness.py','tests/test_atlas_early_observation.py'],
}


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args],text=True).strip()


def prepare(fetch=False):
    for name,pin in PINS.items():
        path=ROOT/'.integration'/name
        if not path.exists():
            if fetch:
                subprocess.run(['git','-C',str(ROOT),'fetch','--no-tags','origin',pin],check=True)
            subprocess.run(['git','-C',str(ROOT),'worktree','add','--detach',str(path),pin],check=True)
        head=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        if head!=pin:raise ValueError('DEPENDENCY_HEAD_MISMATCH:'+name)
        subprocess.run(['git','-C',str(path),'diff','--exit-code','HEAD','--'],check=True)
    staged=ROOT/'.integration/research-kernel'
    if not staged.exists():
        cmd=[sys.executable,str(ROOT/'.integration/research-baseline/tools/first_research_cycle/stage_dependencies.py'),
             '--output',str(staged)]
        if fetch:cmd.append('--fetch')
        subprocess.run(cmd,check=True,cwd=ROOT)


def verify_code_rollback():
    """Reverse the exact checkout delta in a private Git index, never files."""
    base='0dad5acc17172754b741b0e8a97d911436c9f4c5'
    with tempfile.TemporaryDirectory(prefix='aql-code-rollback-') as tmp:
        index=Path(tmp)/'index'
        env={**os.environ,'GIT_INDEX_FILE':str(index)}
        subprocess.run(['git','-C',str(ROOT),'read-tree','HEAD'],env=env,check=True)
        delta=subprocess.check_output(['git','-C',str(ROOT),'diff','--binary','HEAD',base])
        if delta:
            subprocess.run(['git','-C',str(ROOT),'apply','--cached','--binary','-'],
                           input=delta,env=env,check=True)
        restored=subprocess.check_output(['git','-C',str(ROOT),'write-tree'],env=env,text=True).strip()
        if restored!=git('rev-parse',base+'^{tree}'):
            raise ValueError('CODE_ROLLBACK_TREE_MISMATCH')
        return {'status':'PASS_PRIVATE_INDEX_REVERSE_PATCH','base':base,
                'restored_tree':restored,'working_files_modified':False,
                'host_or_data_rollback_executed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare',action='store_true');p.add_argument('--fetch-code',action='store_true')
    p.add_argument('--group',choices=tuple(GROUPS)+('all',),default='all')
    p.add_argument('--output',type=Path,default=ROOT/'integration-acceptance.json')
    a=p.parse_args()
    if a.prepare:prepare(a.fetch_code)
    selected=list(GROUPS) if a.group=='all' else [a.group]
    tests=[t for group in selected for t in GROUPS[group]]
    # Add only explicitly owned new integration seams, never arbitrary test files.
    for pattern in ('tools/realtime_market_feed/test_native_consumers.py',
                    'tools/realtime_market_feed/test_producer_report.py',
                    'tests/test_mcp_producer_link.py','tests/test_mcp_refresh.py'):
        if (ROOT/pattern).is_file() and a.group=='all':tests.append(pattern)
    if not all((ROOT/t).is_file() for t in tests):raise ValueError('REQUIRED_TEST_MODULE_MISSING')
    env={**os.environ,'PYTHONPATH':os.pathsep.join((str(ROOT/'src'),str(ROOT/'tools'),str(ROOT))),
         'BINANCE_LIVE_TEST':'0','PYTHONDONTWRITEBYTECODE':'1'}
    rollback=verify_code_rollback()
    result=subprocess.run([sys.executable,'-B','-m','pytest','-q','--timeout=300',
                          '--junitxml=integration-junit.xml',*tests],cwd=ROOT,env=env)
    evidence={'schema':'aql.integrated-merge.synthetic-acceptance.v1',
        'evidence_grade':'SYNTHETIC_TESTED','tested_checkout_commit':git('rev-parse','HEAD'),
        'tested_tree':git('rev-parse','HEAD^{tree}'),'python':sys.version.split()[0],
        'platform':sys.platform,'pytest_exit':result.returncode,'code_rollback':rollback,'test_modules':tests,
        'dependency_pins':PINS,'host_inspected':False,'original_e2e_run':False,
        'independent_audit_accepted':False,'orders':0,'trading_authority':'NONE'}
    a.output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(result.returncode)

if __name__=='__main__':main()
