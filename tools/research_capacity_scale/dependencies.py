"""Immutable read-only owner dependencies; never edit another lane's source."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

FACTORY='ea4ffd5ce278d93588338122ab6ac1af8ec4da26'
PINS={'discoverer':'c568e3b281795f9eef2165c0e6f571b87157a23c',
      'gateway':'ccd906ac6d770e1364889623cd79bb215f7b5c63',
      'core':'612d1444ff36ed08b63fd0a98bb8d4e71f88cd0d',
      'integration':'c01f526e762a014e5ed84ca3cf695b9d77502ab3'}
PREFIX={'discoverer':'tools/strategy_discoverer_offline/',
        'gateway':'tools/research_evidence_gateway/'}

def git(repo,*args):
    return subprocess.check_output(['git','-c','core.autocrlf=false','-C',str(repo),*args])

def install(repo,destination,*,fetch=False):
    repo,destination=Path(repo).resolve(),Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=True)
    records={}
    if fetch:subprocess.run(['git','-C',str(repo),'fetch','--no-tags','origin',FACTORY],check=True)
    for role,commit in PINS.items():
        if fetch:subprocess.run(['git','-C',str(repo),'fetch','--no-tags','origin',commit],check=True)
        if role not in PREFIX:continue
        paths=git(repo,'ls-tree','-r','--name-only',commit,PREFIX[role]).decode().splitlines()
        for name in paths:
            if not name.endswith('.py') or '/tests/' in name or Path(name).name.startswith('test_'):continue
            raw=git(repo,'show',commit+':'+name);p=destination/name;p.parent.mkdir(parents=True,exist_ok=True)
            if p.exists() and p.read_bytes()!=raw:raise ValueError('CAPACITY_DEPENDENCY_DRIFT')
            p.write_bytes(raw);records[name]={'commit':commit,'sha256':hashlib.sha256(raw).hexdigest()}
    (destination/'pins.json').write_text(json.dumps(records,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return records

def activate(destination):
    destination=Path(destination).resolve()
    records=json.loads((destination/'pins.json').read_text())
    manifest=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if manifest!='d356d605e94508506ff2adb03b3642a447c6c8bc5cc006ae4076dc092e805b87':
        raise ValueError('CAPACITY_DEPENDENCY_MANIFEST')
    for path in destination.rglob('*'):
        if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400:
            raise ValueError('CAPACITY_DEPENDENCY_REPARSE')
        if path.is_file() and path.relative_to(destination).as_posix() not in {*records,'pins.json'}:
            raise ValueError('CAPACITY_DEPENDENCY_EXTRA_SOURCE')
    for name,row in records.items():
        p=destination/name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('CAPACITY_DEPENDENCY_BYTES')
    sys.path.insert(0,str(destination))
    import tools
    if str(destination/'tools') not in tools.__path__:tools.__path__.append(str(destination/'tools'))

def kernel_identity(repo):
    names=('aql_factory_h_execution_comparison_v1.py','aql_factory_h_scientific_lab_v1.py',
           'aql_factory_historical_rule_projection.py','aql_factory_e_research_results_store_v1.py',
           'aql_factory_h_research_package_v1.py')
    rows={}
    for name in names:
        p=Path(repo)/'research_wp_r0'/name
        raw=p.read_text(encoding='utf-8').encode()
        expected=git(repo,'show',FACTORY+':research_wp_r0/'+name).decode().replace('\r\n','\n').encode()
        if raw!=expected:raise ValueError('CAPACITY_FACTORY_SOURCE_DRIFT')
        rows[name]=hashlib.sha256(raw).hexdigest()
    return rows
