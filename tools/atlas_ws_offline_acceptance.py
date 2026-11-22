"""Reproduce the installed pinned runtime assembly; no market/host operations."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from io import BytesIO
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
BASE='d072544427d6b08473c88b2e36d5857cfd8581dc'
TRANSPORT='0a45cb6de6027b6fba54320e07b0faf3317a5382'
WAREHOUSE='5df7f6c9e0d6448db6aa700fa80158b443c5b3db'


def extract(output, version, *paths):
    raw=subprocess.check_output(['git','-C',str(ROOT),'archive','--format=zip',version,*paths])
    with ZipFile(BytesIO(raw)) as bundle:bundle.extractall(output)


def stage(output):
    extract(output,BASE)
    extract(output,TRANSPORT,'tools/binance_live_feed')
    names=('atlas_live_research_cycle.py','atlas_ws_continuity.py','atlas_ws_receive_diagnostics.py','atlas_single_receipt.py',
           'atlas_single_receipt_runner.py','atlas_research_lease.py',
           'atlas_ws_resilience_operator.py','atlas_ws_gap_inventory.py',
           'test_atlas_live_research_cycle.py','test_atlas_ws_receive_diagnostics.py',
           'test_atlas_ws_resilience.py','test_atlas_ws_continuity.py',
           'test_atlas_ws_resilience_operator.py','test_atlas_ws_gap_inventory.py','test_atlas_ws_process_recovery.py')
    for name in names:
        path=ROOT/'tools'/name
        if path.is_file():shutil.copyfile(path,output/'tools'/name)
    return output


def main():
    with tempfile.TemporaryDirectory(prefix='atlas-ws-offline-') as tmp:
        output=stage(Path(tmp)/'runtime')
        wh=Path(tmp)/'warehouse-code'
        subprocess.run(['git','-C',str(ROOT),'worktree','add','--detach',str(wh),WAREHOUSE],check=True,stdout=subprocess.DEVNULL)
        env={**os.environ,'PYTHONPATH':os.pathsep.join((str(output/'src'),str(output))),
             'ATLAS_WAREHOUSE_FIXTURE_CHECKOUT':str(wh),'PYTHONDONTWRITEBYTECODE':'1'}
        tests=[str(p) for p in sorted((output/'tools').glob('test_atlas_ws_*.py'))]
        tests += [str(output/'tools'/n) for n in ('test_atlas_live_research_cycle.py',)]
        try:
            result=subprocess.run([sys.executable,'-B','-m','pytest','-q',*tests],cwd=output,env=env)
        finally:
            subprocess.run(['git','-C',str(ROOT),'worktree','remove','--force',str(wh)],check=True)
        raise SystemExit(result.returncode)


if __name__=='__main__':main()
