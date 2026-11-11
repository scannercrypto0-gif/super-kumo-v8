"""Reproducible research-only entry point; never dispatches orders."""
import argparse
import json
from pathlib import Path
from tools.research_capacity_scale.dependencies import install,kernel_identity
from tools.research_capacity_scale.contracts import make_plan,freeze,canonical
from tools.research_capacity_scale.runtime import run,restore_checkpoint

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('dependencies');d.add_argument('--destination',type=Path,required=True);d.add_argument('--fetch',action='store_true')
    f=sub.add_parser('plan');f.add_argument('--count',type=int,required=True);f.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('run');r.add_argument('--plan',type=Path,required=True);r.add_argument('--root',type=Path,required=True)
    r.add_argument('--deps',type=Path,required=True);r.add_argument('--workers',type=int,default=1);r.add_argument('--control',type=Path)
    r.add_argument('--crash',choices=['before_result_commit','after_report_commit','after_outcome_commit','after_checkpoint_before_ack'])
    s=sub.add_parser('restore');s.add_argument('--root',type=Path,required=True);s.add_argument('--backup',type=Path,required=True);s.add_argument('--expected-sha',required=True)
    args=p.parse_args();repo=Path(__file__).resolve().parents[2]
    if args.command=='dependencies':print(json.dumps({'files':len(install(repo,args.destination,fetch=args.fetch))}))
    elif args.command=='plan':
        plan=make_plan(args.count,kernel_identity(repo));args.output.parent.mkdir(parents=True,exist_ok=True);freeze(args.output,plan);print(plan['sha256'])
    elif args.command=='restore':restore_checkpoint(args.root,args.backup,args.expected_sha)
    else:
        result,metrics=run(args.root,json.loads(args.plan.read_text()),deps=args.deps,workers=args.workers,control=args.control,crash=args.crash)
        print(canonical(dict(sha256=result['sha256'],population=result['population'],metrics=metrics)).decode())

if __name__=='__main__':main()
