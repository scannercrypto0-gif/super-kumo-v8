"""Research-only F2 recovery diagnostic adapter.

The exact owner E: F2_RECOVERY_EVIDENCE.v1 source verifier is owned by
Integration #271 and Core #275. This ONLY accepts its validated, in-memory
already reread actual Core #253 local-query records. Never aliases recovery to
canonical F2, never calls signed F5, never issues Source/Strategy/Factory ACK.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen,require
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from tools.scanner_strategy_f.frozen_diagnostic_contracts import (
    identify_frozen_work235_contracts,
)
from tools.scanner_strategy_f.research_e2e_diagnostic import (
    ADMITTED, diagnostic_original_cohort,
)

SCHEMA="aql.scanner-f.recovery-source-research-e2e-diagnostic.v1"
EXPECTED_RECOVERY="0428e7b02b7b57bded9906c49f956b76816c179cd8659d61e1c7f1af1df68220"


def diagnostic_from_verified_recovery(
    *,warehouse_root,verified_recovery_readbacks,
    recovery_file_sha256,work_specs,
):
    """Scanner contract receiver for Integration's read_recovered_diagnostic.

    Caller must pass the live output, not a SHA-only user-authored fixture.
    Local Core query_local replays every original #253 receipt again; no
    external source-rights or historical PIT proof is implied by this.
    """
    require(recovery_file_sha256==EXPECTED_RECOVERY
            and type(verified_recovery_readbacks) is dict
            and set(verified_recovery_readbacks)==set(ADMITTED),
            "F_DIAG_RECOVERY_VERSION_OR_COHORT_MISMATCH")
    originals={}
    for month in ADMITTED:
        result=verified_recovery_readbacks[month]
        require(type(result) is dict
                and set(result)=={"receipt","native_bars","local_bars"}
                and type(result["receipt"]) is dict
                and type(result["native_bars"]) is list
                and type(result["local_bars"]) is list,
                "F_DIAG_RECOVERY_CORE_RESULT_SHAPE")
        receipt=result["receipt"]
        require(receipt.get("schema")=="aql.core.f2-recovery-readonly-source.v1"
                and receipt.get("month")==month
                and receipt.get("status")=="SOURCE_BACKED_RECOVERY_READBACK_ONLY"
                and receipt.get("recovery_file_sha256")==recovery_file_sha256
                and receipt.get("opaque_recovery_file_pin_verified") is True
                and receipt.get("original_f2_report_sha256") is None
                and receipt.get("historical_pit")=="NOT_ATTESTED"
                and receipt.get("source_ack_sha256") is None
                and receipt.get("strategy_approval_sha256") is None
                and receipt.get("factory_consumer_ack_sha256") is None
                and receipt.get("secretary_state")=="NOT_ENQUEUED"
                and receipt.get("trading_authority")=="NONE"
                and type(receipt.get("bar_count")) is int
                and len(result["native_bars"])==len(result["local_bars"])
                    ==receipt["bar_count"]
                and receipt.get("receipt_sha256")==digest({
                    k:v for k,v in receipt.items() if k!="receipt_sha256"
                }),
                "F_DIAG_RECOVERY_CANNOT_IMPERSONATE_F2_OR_SIGNED_F5")
        # Recompute Core #253 from the actual immutable warehouse. Neither
        # caller-authored query objects nor receipt-only SHA claims are trusted.
        q=query_local(
            warehouse_root,receipt["dataset_id"],1,
            receipt["start_ms"],receipt["end_exclusive_ms"],
            receipt["decision_cutoff_ms"],
            required_source_sha256=receipt["source_zip_sha256"],
            require_complete=True,sqlite_immutable=True,
        )
        require(q["query_sha256"]==receipt.get("core253_local_query_sha256")
                and q["bars"]==result["local_bars"]
                and q["available_bar_count"]==receipt["bar_count"]
                and q["source_bytes_sha256"]==receipt["source_zip_sha256"]
                and q["manifest_integrity_sha256"]==
                    receipt["manifest_integrity_sha256"],
                "F_DIAG_RECOVERY_LOCAL253_RECOMPUTED_SHA_DRIFT")
        # #245 and the dual-map are independently recomputed by Core's
        # read_recovery_diagnostic; Scanner refuses missing/invalid parent
        # identities rather than pretending its local query verifies #245.
        for key in ("core245_native_query_sha256","dual_map_sha256",
                    "warehouse_receipt_sha256",
                    "no_write_tree_fingerprint_sha256"):
            require(type(receipt.get(key)) is str
                    and len(receipt[key])==64
                    and all(c in "0123456789abcdef" for c in receipt[key]),
                    "F_DIAG_RECOVERY_CORE_PARENT_MISSING")
        require(all(a["bar_open_ms"]==b["bar_open_ms"]
                    and a["bar_close_ms"]==b["bar_close_ms"]
                    and a["checksum"]==b["bar_checksum"]
                    and a["bar_close_ms"]<receipt["decision_cutoff_ms"]
                    for a,b in zip(result["native_bars"],q["bars"])),
                "F_DIAG_RECOVERY_NATIVE_LOCAL_BAR_DRIFT")
        originals[month]=q
    identities=identify_frozen_work235_contracts(work_specs)
    out=diagnostic_original_cohort(
        warehouse_root=warehouse_root,month_queries=originals,
        work_specs=identities["work_specs"],
        policy_draft=identities["policy_draft"],
        proposal=identities["proposal"],
        approval_request=identities["approval_request"],
    )
    x=Frozen.restore(out)
    d=x.data
    require(d["decision"]=="DIAGNOSTIC_ONLY_NOT_F5"
            and d["selected"]==0
            and d["native15m_month_bars"]==29376
            and d["diagnostic_evaluated_attempts"]==20
            and d["unknown_feb_aug_attempts"]==4
            and d["source_ack_sha256"] is None
            and d["strategy_approval_sha256"] is None
            and d["factory_consumer_ack_sha256"] is None
            and d["trading_authority"]=="NONE",
            "F_DIAG_RECOVERY_CANNOT_PROMOTE_AUTHORITY")
    return Frozen.build({
        "schema":SCHEMA,
        "source_class":"F2_RECOVERY_EVIDENCE.v1_OWNER_LOCAL",
        "recovery_file_sha256":recovery_file_sha256,
        "original_f2_report_sha256":None,
        "original_f2_report_reconstructed":False,
        "owner_local_source_readback":"DUAL_QUERY_REPLAY",
        "scanner_diagnostic_sha256":x.sha256,
        "frozen_work235_commit":identities["work235_commit"],
        "frozen_strategy_ids":sorted(identities["strategy_identities"]),
        "policy_draft_sha256":identities["policy_draft"]["sha256"],
        "proposal_sha256":identities["proposal"]["sha256"],
        "approval_request_sha256":identities["approval_request"]["sha256"],
        "count_original_bars":29376,
        "attempts":24,
        "diagnostic_evaluated":20,
        "feb_aug_unknown":4,
        "selected":0,
        "historical_pit":"NOT_ATTESTED",
        "signed_f5":"NOT_APPROVED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
        "decision":"RECOVERY_DIAGNOSTIC_ONLY_NOT_F5",
    }).receipt()
