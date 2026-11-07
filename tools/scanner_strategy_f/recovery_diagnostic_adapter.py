"""Research-only F2 recovery diagnostic adapter.

The exact owner E: F2_RECOVERY_EVIDENCE.v1 source verifier is owned by
Integration #271 and Core #275. This ONLY accepts its validated, in-memory
already reread actual Core #253 local-query records. Never aliases recovery to
canonical F2, never calls signed F5, never issues Source/Strategy/Factory ACK.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen,require
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
                and result["receipt"].get("month")==month
                and result["receipt"].get("owner_f2_report_sha256") is None
                and result["receipt"].get("owner_f2_report_pin_verified") is False
                and result["receipt"].get("readback_evidence")==
                    "SOURCE_BACKED_DUAL_QUERY_NO_F2_REPORT_AUTHORITY"
                and result["receipt"].get("historical_pit")=="NOT_ATTESTED"
                and result["receipt"].get("source_ack_sha256") is None
                and result["receipt"].get("strategy_approval_sha256") is None
                and result["receipt"].get("factory_consumer_ack_sha256") is None
                and type(result["local_bars"]) is list,
                "F_DIAG_RECOVERY_CANNOT_IMPERSONATE_F2_OR_SIGNED_F5")
        from research_wp_r0.aql_archive_custody_bridge_v1 import digest
        receipt=result["receipt"]
        require(receipt.get("receipt_sha256")==digest({
            k:v for k,v in receipt.items() if k!="receipt_sha256"
        }) and
            type(result["native_bars"]) is list
            and len(result["native_bars"])==len(result["local_bars"])
                ==receipt["readback_bar_count"],
            "F_DIAG_RECOVERY_RECEIPT_OR_BAR_COUNT_DRIFT")
        # Integration independently checks original publisher raw, source,
        # original Core native #245 and local #253. Scanner re-reads #253
        # instead of relying on a digest provided by the caller.
        q={
            "schema":"aql.core.local-history-query.v1",
            "dataset_id":receipt["dataset_id"],
            "version":receipt["version"],
            "source_bytes_sha256":receipt["source_zip_sha256"],
            "manifest_integrity_sha256":receipt["manifest_integrity_sha256"],
            "start_ms":receipt["start_ms"],
            "end_exclusive_ms":receipt["end_exclusive_ms"],
            "decision_cutoff_ms":receipt["decision_cutoff_ms"],
            "coverage":"COMPLETE",
            "missing_bar_opens":[],
            "required_bar_count":receipt["readback_bar_count"],
            "available_bar_count":receipt["readback_bar_count"],
            "bars":result["local_bars"],
            "source_availability":"RETROSPECTIVE_NON_PIT",
            "historical_pit":"NOT_ATTESTED",
            "universe":"NOT_ATTESTED",
        }
        q["query_sha256"]=digest(q)
        require(q["query_sha256"]==receipt["core253_local_query_sha256"],
                "F_DIAG_RECOVERY_LOCAL253_RECOMPUTED_SHA_DRIFT")
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
