"""Manual, source-pinned repair of the installed d582 permit-byte mismatch.

No deployment, source calls or task changes. Original raw permit must exist.
Caller holds the supervisor lock. Existing collector lease is also required.
"""
import argparse
import json
from pathlib import Path
import sys
import sqlite3
import time
import uuid
import importlib.util
_spec=importlib.util.spec_from_file_location('atlas_permit_repair_operator',Path(__file__).with_name('atlas_ws_resilience_operator.py'))
op=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(op)

EXPECTED=dict(config_sha256='857bea957d1da3fa1ef1c01ace44a0bfda27f84c2750523184455936a48f2cf2',
    authorization_sha256='562300683daa9cd3640a4be63ab96a5c71a3d9e4d70a9d64f419e1d84aa5f576',
    candidate_commit='d5828cba2ca151e336d0aedbafc778834de6854a',
    backup='ws-recovery-backup-0580297e58284ff4aa246fc6031809c3',
    backup_manifest_sha256='4cbe2108668387345fcd6ec13da508d442f2cc107d4556970b79ced388275b5b')


def repair(config,permit_dir,owner_ref,now,expected=EXPECTED):
    op.need(type(owner_ref) is str and owner_ref.strip(),'EXPLICIT_REPAIR_OWNER_DECISION_REQUIRED')
    config=op.safe(config);root=config.parent
    with op.collector_lease(root):
        op.need(op.digest(op.read(config))==expected['config_sha256'],'REPAIR_CONFIG_DRIFT')
        for name in ('segment-execution.active.json','operator-recovery.active.json','operator-deployment.in-progress'):
            op.need(not (root/name).exists(),'REPAIR_INITIAL_RECOVERY_ALREADY_CONSUMED_OR_UNCERTAIN')
        authority=op.load(root/'continuous-research.authorized.json')
        authpin=expected['authorization_sha256']
        op.need(authority.get('authorization_sha256')==authpin and
                authority.get('config_sha256')==expected['config_sha256'],'REPAIR_AUTHORITY_DRIFT')
        backup=op.safe(root/expected['backup'],exists=False)
        op.need(op.digest(op.read(backup/'manifest.json'))==expected['backup_manifest_sha256'],'REPAIR_BACKUP_MANIFEST_PIN')
        deployed=op.load(backup/'deployment-receipt.json')
        op.need(deployed.get('candidate_commit')==expected['candidate_commit'] and
                deployed.get('config_sha256')==expected['config_sha256'] and
                deployed.get('authorization_sha256')==authpin and deployed.get('continuous_research') is True,
                'REPAIR_DEPLOYMENT_IDENTITY')
        held=op.read(root/'hold.json')
        op.need(held==op.read(backup/'hold.json'),'REPAIR_ORIGINAL_HOLD_CHANGED')
        for item in op.load(config)['files']:
            op.need(op.digest(op.read(item['path']))==item['sha256'],'REPAIR_RUNTIME_PIN')
        claimed=root/'operator-authorizations'/(authpin+'.claimed')
        previous=op.read(claimed,65536)
        # Restore authentic original bytes, never rename a digest or synthesize
        # publisher/owner source from a semantically equivalent JSON document.
        candidates=list(Path(permit_dir).glob('atlas-continuous-permit-*.json'))
        op.need(len(candidates)<=1000,'REPAIR_ORIGINAL_SEARCH_BOUND')
        matches=[]
        for path in candidates:
            raw=op.read(path,65536)
            if op.digest(raw)==authpin:matches.append(raw)
        op.need(bool(matches),'REPAIR_ORIGINAL_PERMIT_BYTES_UNAVAILABLE')
        original=matches[0]
        permit=json.loads(original.decode('utf-8-sig'),object_pairs_hook=op.pairs)
        op.need(op.canonical(permit)==previous or previous==original,'REPAIR_NOT_KNOWN_SERIALIZATION_DEFECT')
        op.need(permit.get('candidate_commit')==expected['candidate_commit'] and permit.get('continuous_research') is True
                and permit.get('continuity_policy_sha256')==op.continuity_pin()
                and permit.get('allow_explicit_missing_intervals') is True
                and permit.get('max_connections')==2 and permit.get('max_segments')==1
                and permit.get('orders')==0 and permit.get('trading_authority')=='NONE','REPAIR_ORIGINAL_SCOPE')
        ticketpath=root/'operator-resume.authorized.json'
        tickets=[ticketpath] if ticketpath.exists() else []
        rejected=list(root.glob('operator-resume.rejected-*.json'))
        op.need(len(rejected)<=1000,'REPAIR_REJECTED_SEARCH_BOUND')
        tickets+=rejected
        matching=[]
        for path in tickets:
            t=op.load(path)
            if t.get('authorization_sha256')==authpin and t.get('config_sha256')==expected['config_sha256']:
                op.need(t.get('hold_sha256')==op.digest(held),'REPAIR_TICKET_HOLD_DRIFT')
                for name,field in (('reset-recovery.claimed','claimed_sha256'),('reset-recovery.pending','pending_sha256')):
                    op.need(op.optional_pin(root/name)==t.get(field),'REPAIR_TICKET_EVIDENCE_DRIFT')
                matching.append((path,t))
        op.need(len(matching)==1,'REPAIR_INITIAL_TICKET_NOT_UNIQUE')
        source,ticket=matching[0]
        evidence=root/('permit-byte-repair-'+uuid.uuid4().hex)
        evidence.mkdir()
        op.durable(evidence/'claimed-before.bin',previous,create=True)
        op.durable(evidence/'original-permit.bin',original,create=True)
        op.durable(evidence/'original-resume-ticket.json',op.read(source),create=True)
        op.durable(claimed,original)
        # This is an explicitly invoked manual repair under the installed
        # continuous permission, not a scheduled renewal or another deployment.
        ticket['issued_ms']=now;ticket['expires_ms']=now+1800000
        ticket['repair_owner_decision_ref']=owner_ref
        if source==ticketpath:source.rename(evidence/'pending-ticket.archived.json')
        op.durable(ticketpath,op.canonical(ticket),create=True)
        result=dict(schema='atlas.ws.permit-byte-repair.v1',status='ORIGINAL_PERMIT_BYTES_RESTORED_INITIAL_RESUME_REQUEUED',
            config_sha256=expected['config_sha256'],authorization_sha256=authpin,
            previous_claimed_sha256=op.digest(previous),restored_claimed_sha256=op.digest(original),
            evidence=evidence.name,owner_decision_ref=owner_ref,initial_resume_issued_ms=now,
            initial_resume_expires_ms=now+1800000,original_hold_preserved=True,task_changes=0,
            deployment_repeated=False,source_calls=0,orders=0,trading_authority='NONE')
        op.durable(evidence/'repair-receipt.json',op.canonical(result),create=True)
        return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True,type=Path)
    p.add_argument('--expected-commit',required=True)
    p.add_argument('--permit-dir',required=True,type=Path);p.add_argument('--owner-ref',required=True)
    a=p.parse_args();op.verify_repo(Path(__file__).resolve().parents[1],a.expected_commit)
    print(json.dumps(repair(a.config,a.permit_dir,a.owner_ref,time.time_ns()//1000000),sort_keys=True))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError) as exc:
        import re
        reason=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{1,119}',str(exc)) else 'REPAIR_PRIVATE_STATE_FAILURE'
        print(json.dumps(dict(status='PERMIT_REPAIR_BLOCKED',reason=reason,orders=0,trading_authority='NONE')))
        raise SystemExit(2)
