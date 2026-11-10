"""Git-source staging only; never acquires market data or runs producer suites."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fetch',action='store_true');args=p.parse_args()
    plan=json.loads(Path(__file__).with_name('market-plan.json').read_text())
    assert not args.output.exists(),'NEW_DEPENDENCY_DIRECTORY_REQUIRED'
    roles=dict(factory='factory291',discoverer='discoverer276',scanner='scanner277',core='core290',work235='work235',scanner_b='scanner_b')
    for role,key in roles.items():
        commit=plan['dependency_heads'][key]
        if args.fetch:subprocess.run(['git','fetch','--no-tags','origin',commit],check=True)
        raw=subprocess.check_output(['git','-c','core.autocrlf=false','-c','core.eol=lf','archive',commit])
        dest=args.output/role;dest.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for item in archive.getmembers():
                path=Path(item.name)
                if item.isfile() and not path.is_absolute() and '..' not in path.parts and item.name.endswith(('.py','.json')):
                    out=dest/path;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(archive.extractfile(item).read())
    for item in plan['dependency_files']:
        assert hashlib.sha256((args.output/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
    print('PINNED_DEPENDENCY_BYTES_VERIFIED')
