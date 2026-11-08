"""One owner-local bounded March H2 evidence recovery / optional new v2 signing.

No original H2 execution. No source files written. All four artifacts created
only after authentic publisher+actual Core245/Core253+native Scanner proof.
This script runs on the OWNER machine in a pinned isolated code overlay.
It does NOT enroll a key or invent missing original Core stage/receipts.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile

from tools.atlas_h2_binance_public_lane_v1 import (
    LANE_SCHEMA, verify_public_month, validate_native_manual_third_ast,
)
from tools.atlas_h2_owner_identity_v2 import (
    ENVELOPE_SCHEMA, identity_metadata_from_key,
    inspect_forward_owner_assertion,
)
from tools.atlas_h2_owner_research_authority_v1 import (
    SCHEMA as ASSERTION_SCHEMA, AUTHORITY, COST_SCHEMA,
    SCOPE_DOMAIN, COST_DOMAIN, _canonical, _digest,
)
from tools.atlas_h2_owner_local_one_shot_v1 import (
    OWNER_LIMITED_COSTS, PINS, fingerprint, sha_file,
    verified_local_sqlite_snapshot, native_receipt_check,
)
from tools.atlas_h2_owner_personal_batch_v1 import scope_commitment

START=1709251200000
END=1711929600000
DATASET="BINANCE-SPOT-BTCUSDT-15M-2024-03"
OWNER_REF="#271/6720832849"


class RecoveryBlocked(ValueError):
    pass


def need(condition,reason):
    if not condition:
        raise RecoveryBlocked(reason)


def _write_exclusive(path, obj):
    raw=json.dumps(obj,sort_keys=True,ensure_ascii=True,
                   separators=(",",":"),allow_nan=False).encode("ascii")
    with Path(path).open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def _bounded_warehouse(private_root):
    root=Path(private_root)
    need(root.is_dir() and not root.is_symlink(),
         "ORIGINAL_PRIVATE_ROOT_NOT_AVAILABLE")
    # Exactly one bounded selection, NOT a repeated count/ZIP inventory.
    match=[]
    for p in root.rglob("warehouse.sqlite"):
        if p.is_file() and not p.is_symlink():
            match.append(p.parent)
        if len(match)>1: break
    need(len(match)==1,"MISSING_OR_AMBIGUOUS_ORIGINAL_WAREHOUSE_SQLITE")
    return match[0]


def _real_core_dual(snapshot, source_sha):
    """Core #275 exact native and local proof from retained original stage."""
    from research_wp_r0.aql_archive_custody_bridge_v1 import (
        decode, digest, verify_packet, raw_sha,
    )
    from research_wp_r0.aql_core_backbone_local_v1 import query_local
    from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
    from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
    from research_wp_r0.historical_library import (
        HistoricalBar, HistoricalLibrary, BarQuality, SourceType,
        DataAvailabilityKind, validate_bars,
    )
    db=sqlite3.connect((Path(snapshot)/"warehouse.sqlite").as_uri()+
                       "?mode=ro&immutable=1",uri=True)
    try:
        rows=db.execute(
            "SELECT dataset_id,generation,source_sha,manifest_sha,packet_sha,"
            "admission_json FROM generations WHERE source_sha=?",
            (source_sha,)).fetchall()
    except sqlite3.Error:
        raise RecoveryBlocked("MISSING_ORIGINAL_CORE_BRIDGE_GENERATIONS") from None
    finally:
        db.close()
    candidates=[r for r in rows if r[0].startswith("BINANCE-SPOT-BTCUSDT-15M-")
                and type(r[1]) is int and r[1]>0]
    need(len(candidates)==1,"MISSING_OR_AMBIGUOUS_ORIGINAL_CORE_BRIDGE_STAGE")
    dataset,version,source,manifest_sha,packet_sha,admission_raw=candidates[0]
    need(dataset==DATASET,
         "ORIGINAL_DATASET_IDENTITY_MISMATCH_STOP")
    admission=json.loads(admission_raw)
    need(digest({k:v for k,v in admission.items()
                 if k!="manifest_record_sha256"})==
         admission.get("manifest_record_sha256")
         and admission.get("source_bytes_sha256")==source
         and admission.get("manifest_integrity_sha256")==manifest_sha,
         "MISSING_ORIGINAL_AUTHENTIC_CORE_ADMISSION")
    folder=Path(snapshot)/"stage"/packet_sha
    need((folder/"packet.json").is_file()
         and (folder/"source.bin").is_file(),
         "MISSING_ORIGINAL_CORE_BRIDGE_STAGE")
    packet=decode((folder/"packet.json").read_bytes())
    raw=(folder/"source.bin").read_bytes()
    verify_packet(packet,raw)
    need(packet["packet_sha256"]==packet_sha
         and raw_sha(raw)==source,
         "ORIGINAL_CORE_BRIDGE_PARENT_OR_SHA_MISMATCH")
    spec=packet["spec"]
    need((spec["dataset_id"],spec["version"],spec["interval"],
          spec["start_ms"],spec["end_exclusive_ms"])==
         (dataset,version,"15m",START,END)
         and spec["test_only"] is False,
         "ORIGINAL_BRIDGE_MARCH_SCOPE_OR_SYNTHETIC_PARENT")
    bars=[HistoricalBar(**{
        **row,"quality":BarQuality(row["quality"]),
        "source":SourceType(row["source"]),
        "availability_kind":DataAvailabilityKind(row["availability_kind"]),
    }) for row in packet["bars"]]
    checked,manifest=validate_bars(bars,spec["symbol"],spec["interval"])
    manifest=replace(
        manifest,dataset_id=dataset,version=version,
        exchange=spec["exchange"],market=spec["market"],
        source_label=spec["source_label"],created_at_ms=spec["as_of_ms"],
        parent_version=version-1 if version>1 else None,
        lineage_reason=spec["correction_reason"],source_hash=source)
    need(manifest.manifest_integrity_hash==manifest_sha,
         "ORIGINAL_CORE_REBUILT_MANIFEST_MISMATCH")
    library=HistoricalLibrary()
    library.register(dataset,checked,manifest)  # IN-MEMORY ONLY
    request={
        "schema":REQUEST_SCHEMA,"dataset_id":dataset,"version":version,
        "start_ms":START,"end_exclusive_ms":END,
        "decision_cutoff_ms":END,
        "require_complete":True,"confirmed_only":False,
    }
    native=query_price_custody(
        library,request,expected_source_sha256=source,
        expected_manifest_integrity_sha256=manifest_sha)
    local=query_local(
        snapshot,dataset,version,START,END,END,
        required_source_sha256=source,require_complete=True,
        sqlite_immutable=True)
    need(native["schema"]=="aql.core.historical-price-custody-query.v1"
         and local["schema"]=="aql.core.local-history-query.v1"
         and native["status"]=="OK"
         and native["coverage"]==local["coverage"]=="COMPLETE"
         and native["source_bytes_sha256"]==local["source_bytes_sha256"]==source
         and native["manifest_integrity_sha256"]==
             local["manifest_integrity_sha256"]==manifest_sha
         and native["decision_cutoff_ms"]==
             local["decision_cutoff_ms"]==END
         and native["required_bar_count"]==
             native["available_bar_count"]==
             local["required_bar_count"]==
             local["available_bar_count"]==2976
         and native["missing_bar_opens"]==local["missing_bar_opens"]==[]
         and native["price_query_sha256"]!=local["query_sha256"],
         "ORIGINAL_CORE_DUAL_COMPLETE_OR_CUTOFF_UNVERIFIED")
    need(all(
        a["bar_open_ms"]==b["bar_open_ms"]
        and a["bar_close_ms"]==b["bar_close_ms"]
        and a["checksum"]==b["bar_checksum"]
        and a["bar_close_ms"]<END
        for a,b in zip(native["bars"],local["bars"])
    ) and len(native["bars"])==len(local["bars"])==2976,
         "ORIGINAL_CORE_DUAL_ROW_DRIFT")
    return native,local,dataset,version,manifest_sha


def _manual_ast():
    """Scanner #277's declared manual strategy recipe, NO duplicate examples."""
    from research_wp_r0.strategy_definition import StrategyDefinition
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
    from tools.strategy_service_offline.run import FIXTURES
    from tools.scanner_strategy_f import research_strategy_plugin as scanner
    from tools.scanner_strategy_f.frozen_diagnostic_contracts import FROZEN
    from tools.strategy_service_offline.common import Frozen
    fixtures=json.loads((FIXTURES/"strategies.json").read_text("utf-8"))
    need(len(fixtures)==2,"MANUAL_THIRD_FROZEN_FIXTURES_MISSING")
    parents=[StrategyDefinition.from_dict(
        f["payload"]["definition"],registry=IndicatorRegistryV2())
        for f in fixtures]
    need({p.spec["strategy_id"] for p in parents}==
         {"test_momentum","test_reversion"}
         and all(p.digest==FROZEN[p.spec["strategy_id"]]["definition_digest"]
                 for p in parents),
         "MANUAL_THIRD_FROZEN_PARENT_MISMATCH")
    spec=copy.deepcopy(parents[0].spec)
    spec["strategy_id"]="h_manual_distinct_test"
    spec["indicators"][0]["parameters"]["period"]=5
    spec["entry"]["right"]["value"]=99
    definition=StrategyDefinition(spec,registry=IndicatorRegistryV2())
    receipt=definition.to_dict()
    need(definition.digest not in {p.digest for p in parents}
         and definition.spec["scope"]=="RESEARCH_ONLY"
         and definition.spec["timing"] == {
             "decision":"CONFIRMED_CLOSE",
             "entry_execution":"NEXT_ELIGIBLE_OPEN",
             "ambiguity":"REJECT",
         },
         "MANUAL_THIRD_DISTINCTNESS_OR_TIMING_FAILED")
    config_sha=scanner.manual_config_digest(receipt)
    plugin=scanner.register_strategy_plugin(
        receipt,config_digest=config_sha,
        source_spec_receipt=None,origin="MANUAL",candidate_sha256=None)
    pd=Frozen.restore(plugin).data
    need(pd["strategy_id"]=="h_manual_distinct_test"
         and pd["definition_digest"]==definition.digest
         and pd["config_digest"]==config_sha
         and pd["input_origin"]=="MANUAL"
         and pd["candidate_sha256"] is None
         and pd["policy_status"]=="RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL"
         and pd["trading_authority"]=="NONE",
         "MANUAL_THIRD_UNAUTHORIZED_PLUGIN")
    return receipt,config_sha,pd["evaluator_code_sha256"]


def prepare_owner_private_evidence(*,source_zip,private_root,output_root,
                                   evidence_dir,identity_dir,confirm_sign,
                                   public_fetcher=None):
    """No H2 run. Write exactly FOUR outputs only when all parents authentic."""
    from tools.atlas_h2_binance_public_lane_v1 import fetch_official
    from tools.atlas_h2_owner_local_one_shot_v1 import (
        OWNER_LIMITED_COSTS, digest as operator_digest,
    )
    from tools.atlas_h2_owner_personal_batch_v1 import (
        scope_commitment,
    )
    need(confirm_sign is True,"OWNER_EXPLICIT_CONTEMPORANEOUS_SIGN_REQUIRED")
    source=Path(source_zip)
    private=Path(private_root)
    out=Path(output_root)
    evidence=Path(evidence_dir)
    identity_root=Path(identity_dir)
    need(source.is_file() and not source.is_symlink()
         and source.name=="BTCUSDT-15m-2024-03.zip"
         and private.is_dir() and evidence.is_dir()
         and out.is_dir() and identity_root.is_dir()
         and not evidence.is_symlink() and not out.is_symlink()
         and not any(evidence.iterdir())
         and not any((evidence/name).exists() for name in (
             "technical-intake.json","owner-personal-assertion.json",
             "core245-native-receipt.json","manual-third-ast.json")),
         "ORIGINAL_OR_PRIVATE_OUTPUT_PATH_UNSAFE")
    need(not str(evidence).startswith(str(private))
         and not str(out).startswith(str(private))
         and not str(identity_root).startswith(str(private)),
         "PRIVATE_OUTPUT_OR_SIGNER_OVERLAPS_ORIGINAL")
    key_path=identity_root/"owner-signing.key"
    meta=json.loads((identity_root/"owner-identity.json").read_text("utf-8"))
    rev=json.loads((identity_root/"owner-revocations.json").read_text("utf-8"))
    key=key_path.read_bytes()
    expected=identity_metadata_from_key(key,meta["created_at_utc"])
    need(meta==expected and meta["key_id"] not in rev["revoked_key_ids"],
         "OWNER_NEW_KEY_IDENTITY_OR_REVOCATION_INVALID")
    # Exact actual publisher HTTPS bytes, not owner's adjacent local checksum.
    publisher=verify_public_month(
        "2024-03",fetcher=public_fetcher or fetch_official)
    need(publisher["bar_count"]==2976
         and publisher["first_open_ms"]==START
         and publisher["end_exclusive_ms"]==END,
         "PUBLISHER_MARCH_2024_NOT_COMPLETE")
    before=sha_file(source)
    need(before==publisher["zip_bytes_sha256"],
         "OWNER_ARCHIVE_NOT_IDENTICAL_TO_PUBLISHER")
    warehouse=_bounded_warehouse(private)
    candidate_vaults=[p for p in (private/"vault",private/"raw-vault",
                                   private/"RawVault",private/"raw_vault")
                      if p.is_dir() and not p.is_symlink()]
    need(len(candidate_vaults)==1,
         "ORIGINAL_VAULT_EXACT_PATH_NOT_UNAMBIGUOUS")
    vault=candidate_vaults[0]
    warehouse_before=fingerprint(warehouse)
    vault_before=fingerprint(vault)
    with tempfile.TemporaryDirectory(dir=out,prefix="core-recovery-") as tmp:
        snapshot=verified_local_sqlite_snapshot(warehouse,tmp)
        native,local,dataset,version,manifest_sha=_real_core_dual(snapshot,before)
    ast,config_sha,evaluator_sha=_manual_ast()
    # Code hash is an immutable exact module hash for TEST_ONLY identity.
    from research_wp_r0 import aql_factory_h_generic_signal_adapter_v1 as factory
    factory_sha=sha_file(factory.__file__)
    need(sha_file(source)==before
         and fingerprint(warehouse)==warehouse_before
         and fingerprint(vault)==vault_before,
         "ORIGINAL_SOURCE_CHANGED_DURING_READ_ONLY_PREP")
    signed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    identity_binding=_digest({"identity":meta,"signed_at_utc":signed_at})
    tech={
        "schema":LANE_SCHEMA,"owner_authorization_ref":OWNER_REF,
        "one_time_scope_authorized":True,
        "warehouse_root":str(warehouse),"vault_root":str(vault),
        "local_source_zip":str(source),"dataset_id":dataset,
        "version":version,"month":"2024-03",
        "start_ms":START,"end_exclusive_ms":END,
        "decision_cutoff_ms":END,"source_bytes_sha256":before,
        "manifest_integrity_sha256":manifest_sha,
        "native_receipt_file_sha256":hashlib.sha256(json.dumps(
            native,sort_keys=True,separators=(",",":"),
            ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest(),
        "strategy_file_sha256":hashlib.sha256(json.dumps(
            ast,sort_keys=True,separators=(",",":"),
            ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest(),
        "strategy_definition_sha256":ast["digest"],
        "strategy_id":"h_manual_distinct_test",
        "factory_code_sha256":factory_sha,
        "experiment_id":"RESEARCH-H-GENERIC-MARCH-2024-OWNER-ONE",
    }
    policy={
        "schema":COST_SCHEMA,"costs":OWNER_LIMITED_COSTS.copy(),
        "market":"SPOT","direction":"LONG",
        "research_class":"RETROSPECTIVE_NON_PIT",
        "authorization_class":"OWNER_EXPLICIT_COST_ONLY",
        "single_use_experiment_id":tech["experiment_id"],
    }
    scope={
        "dataset_id":dataset,"version":version,
        "month":"2024-03","start_ms":START,
        "end_exclusive_ms":END,"decision_cutoff_ms":END,
        "source_bytes_sha256":before,
        "manifest_integrity_sha256":manifest_sha,
        "core245_native_receipt_sha256":native["price_query_sha256"],
        "core253_query_sha256":local["query_sha256"],
        "strategy_id":"h_manual_distinct_test",
        "strategy_definition_sha256":ast["digest"],
        "strategy_config_sha256":config_sha,
        "evaluator_code_sha256":evaluator_sha,
        "cost_policy_sha256":_digest(policy),
        "experiment_id":tech["experiment_id"],
        "owner_authorization_ref":scope_commitment(
            tech,out,identity_binding=identity_binding),
        "one_use_nonce":secrets.token_hex(16),
        "research_class":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "publisher_pit_attested":False,
        "explicit_readonly_no_export":True,
        "source_output_separate":True,
        "single_use":True,
    }
    assertion={
        "schema":ASSERTION_SCHEMA,
        "authority_class":AUTHORITY,
        "independent_license_review_status":"NOT_ATTESTED",
        "scope":scope,"cost_policy":policy,
        "owner_scope_mac":hmac.new(key,SCOPE_DOMAIN+_canonical(scope),
                                   hashlib.sha256).hexdigest(),
        "owner_cost_mac":hmac.new(key,COST_DOMAIN+_canonical(policy),
                                  hashlib.sha256).hexdigest(),
    }
    envelope={
        "schema":ENVELOPE_SCHEMA,"identity":meta,
        "signed_at_utc":signed_at,"assertion":assertion,
    }
    inspected=inspect_forward_owner_assertion(
        envelope,owner_key_file=key_path,revocation_registry=rev)
    need(inspected["original_h2_execution_permitted"] is False
         and inspected["identity_binding_sha256"]==identity_binding,
         "OWNER_FORWARD_IDENTITY_LOCAL_READBACK_FAILED")
    # One consistent private commit with exclusive no-overwrite writes.
    # Only these four genuine evidence outputs; never expose source to GitHub.
    created=[]
    try:
        for filename,doc in (
            ("core245-native-receipt.json",native),
            ("manual-third-ast.json",ast),
            ("technical-intake.json",tech),
            ("owner-personal-assertion.json",envelope),
        ):
            _write_exclusive(evidence/filename,doc)
            created.append(evidence/filename)
    except Exception:
        for p in created:
            p.unlink(missing_ok=True)
        raise
    need(sha_file(source)==before
         and fingerprint(warehouse)==warehouse_before
         and fingerprint(vault)==vault_before,
         "ORIGINAL_CHANGED_AFTER_PRIVATE_EVIDENCE_PREP")
    return {
        "status":"FOUR_AUTHENTIC_OWNER_LOCAL_ARTIFACTS_PREPARED_NOT_RUN",
        "owner_key_id":meta["key_id"],
        "signed_at_utc":signed_at,
        "publisher_source_sha256":before,
        "core245_query_sha256":native["price_query_sha256"],
        "core253_query_sha256":local["query_sha256"],
        "strategy_definition_sha256":ast["digest"],
        "cost_policy_sha256":_digest(policy),
        "one_use_scope_sha256":_digest(scope),
        "historical_pit":"NOT_ATTESTED",
        "third_party_rights":"UNVERIFIED",
        "original_h2_executed":False,
    }
