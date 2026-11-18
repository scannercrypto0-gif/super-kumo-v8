"""B3 local capture-container admission/readback; never a source/PIT authority.

The exact existing Core B2 artifact is synthetic TEST_ONLY. Storing its original
bytes cannot establish custody of the source bytes claimed INSIDE its records.
No protected Core/Factory import, network, market transform or Vault redesign.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .schema import RawObjectMeta, logical_identity_key
from .vault import RawVault

CORE_INPUT_SHA = '42005d09e3674420ddd8a761d40540c8e6509e8e79943d1f6a9821f692823b09'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False)+'\n').encode()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _links(core):
    require(core.get('schema_version') == 'aql.b2-core-factory-integrity-input.v1'
            and core.get('evidence_class') == 'TEST_ONLY_CONTROLLED_SYSTEM_INPUT'
            and core.get('original_pit_verified') is False, 'CORE_TEST_ONLY_BOUNDARY')
    schedules = core['schedule']
    require(core['n'] == 2 and len(schedules) == 2
            and len({s['pair_id'] for s in schedules}) == 2, 'N_TWO_SCHEDULE')
    records = core['original_candidates_test_only']
    expected = {(s['pair_id'],a) for s in schedules for a in ('BASE','SHADOW')}
    require(len(records) == 4 and {(r['pair_id'],r['arm']) for r in records} == expected,
            'FOUR_ORIGINAL_CANDIDATES')
    fields = ('pair_id','arm','f1_record_sha256','c2_identity','source_id',
              'source_version','source_bytes_sha256','correction_generation',
              'correction_lineage_sha256','source_available_at_ms',
              'decision_cutoff_ms')
    return [{field:r[field] for field in fields} for r in records]


def admit_core_container(raw: bytes, root: Path):
    """Call actual RawVault.admit/read/manifest_entries, retaining original bytes.

    Metadata describes the TEST_ONLY capture CONTAINER, not its unavailable
    claimed market source. Its local generation0 does NOT translate Core 'g1'.
    Reopening the same retained vault preserves the first admission metadata.
    """
    require(type(raw) is bytes and sha(raw) == CORE_INPUT_SHA, 'CORE_PINNED_BYTES_CHANGED')
    core = json.loads(raw)
    links = _links(core)
    identity = dict(vendor='CORE_B2_TEST_ONLY_CAPTURE_CONTAINER',instrument='TEST_ONLY',
                    market='NOT_MARKET_DATA',interval='15m',source_format='JSON_LINES',
                    format_version='aql.b2-core-factory-integrity-input.v1',
                    coverage_start_utc='1970-01-01T00:00:00Z',
                    coverage_end_utc='1970-01-01T00:15:00Z')
    lid = logical_identity_key(**identity)
    vault = RawVault(root)
    existing = [x for x in vault.manifest_entries() if x['logical_identity_key'] == lid]
    require(len(existing) <= 1, 'DUPLICATE_CONTAINER_MANIFEST')
    if existing:
        meta = RawObjectMeta.from_dict(existing[0])
        require(all(getattr(meta,k) == v for k,v in identity.items())
                and meta.content_sha256 == CORE_INPUT_SHA, 'CONTAINER_MANIFEST_IDENTITY')
    else:
        meta = RawObjectMeta(schema_version='raw_object.v1',content_sha256=sha(raw),
            byte_length=len(raw),**identity,coverage_status='UNKNOWN',
            evidence_class='FIXTURE_SYNTHETIC',trust_status='UNVERIFIED',
            original_filename='core-b2-integrity-input.json',
            capture_provenance='Core B2 artifact13084853700, original TEST_ONLY container bytes; not original market source/PIT',
            archive_member_path='',archive_member_sha256='',logical_identity_key=lid,
            admitted_at_utc=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),
            correction_generation=0,parent_content_sha256='')
    admitted = vault.admit(raw,meta)  # genuine API, not a fabricated receipt
    restored = vault.read(admitted.content_sha256)  # genuine read+SHA check
    require(restored == raw, 'VAULT_READBACK_BYTES_DIFFER')
    manifest_raw = (Path(root)/'manifest.jsonl').read_bytes()
    entries = vault.manifest_entries()
    require(entries == [meta.to_dict()], 'DEDICATED_CONTAINER_VAULT_MANIFEST_MISMATCH')
    receipt = dict(schema='aql.b3.local-vault-readback.v1',
        evidence_class='LOCAL_VAULT_SOFTWARE_SEAM_NOT_EXTERNAL_CUSTODY',
        object_role='ORIGINAL_TEST_ONLY_CAPTURE_CONTAINER_NOT_F1_MARKET_SOURCE',
        core_input_sha256=sha(raw),object_byte_length=len(raw),
        object_content_sha256=sha(restored),logical_identity_key=lid,
        manifest_bytes_sha256=sha(manifest_raw),manifest_entry=meta.to_dict(),
        original_f1_links=links,
        actual_admit_called=True,actual_read_called=True,
        source_publication_clock='UNKNOWN_NOT_SUPPLIED',
        correction_publication_clock='UNKNOWN_NOT_SUPPLIED',
        external_issuer_custody_clock_proven=False,
        independent_source_parent_manifest='NOT_SUPPLIED',
        original_claimed_source_bytes='NOT_SUPPLIED',
        status='LOCAL_VAULT_SOFTWARE_SEAM_PASS')
    receipt['receipt_sha256'] = sha(canonical(receipt))
    return receipt,restored,manifest_raw


def verify_local_readback(root: Path, receipt: dict):
    """Recheck actual retained bytes AND exact manifest, not self-reported flags.

    Success establishes local software integrity only. No external witness or
    proof_verifier=True is produced, even if a caller adds 'VERIFIED' flags.
    """
    require(receipt.get('schema') == 'aql.b3.local-vault-readback.v1', 'RECEIPT_SCHEMA')
    require(receipt.get('receipt_sha256') == sha(canonical({
        k:v for k,v in receipt.items() if k != 'receipt_sha256'})), 'RECEIPT_DIGEST')
    require(receipt['evidence_class'] == 'LOCAL_VAULT_SOFTWARE_SEAM_NOT_EXTERNAL_CUSTODY'
            and receipt['external_issuer_custody_clock_proven'] is False,
            'LOCAL_RECEIPT_CANNOT_ASSERT_EXTERNAL_AUTHORITY')
    manifest = (Path(root)/'manifest.jsonl').read_bytes()
    require(sha(manifest) == receipt['manifest_bytes_sha256'], 'MANIFEST_BYTES_CHANGED')
    entries = [json.loads(line) for line in manifest.splitlines() if line]
    require(entries == [receipt['manifest_entry']], 'MANIFEST_ENTRY_MISMATCH')
    meta = entries[0]
    require(meta['content_sha256'] == receipt['object_content_sha256'] == CORE_INPUT_SHA
            and meta['logical_identity_key'] == receipt['logical_identity_key'],
            'RECEIPT_OBJECT_BINDING')
    data = RawVault(root).read(CORE_INPUT_SHA)
    require(len(data) == receipt['object_byte_length'] == meta['byte_length'], 'OBJECT_LENGTH')
    require(_links(json.loads(data)) == receipt['original_f1_links'], 'ORIGINAL_F1_LINKS_CHANGED')
    return data
