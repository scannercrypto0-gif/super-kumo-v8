"""Scanner F3 — frozen Work235 identity resolver (source files, not approval).

The Work235 fixture is an original frozen *strategy definition*, but its
TEST_ONLY/SYNTHETIC provenance is never inherited as BTCUSDT source authority.
Policy proposal/request/draft are deterministic review contracts NOT approvals.
No original F2 report, F2_RECOVERY_EVIDENCE, SourceACK, StrategyApproval,
ConsumerACK, F5 signature or historical PIT receipt is minted here.
"""
from __future__ import annotations

from pathlib import Path
import json

from tools.strategy_service_offline.common import Frozen, require

SCHEMA="aql.scanner-f.frozen-diagnostic-contract-identities.v1"
WORK235_COMMIT="6acbcc7fc243b132f58170df4c6469bbf7f4eff8"
WORK235_BLOB="c27eb5aa70a6d671791ba1e55e9b078a272b611f"
WORK235_PATH="tools/strategy_service_offline/fixtures/strategies.json"

FROZEN={
    "test_momentum":{
        "spec_sha256":"20ae2d83a8d315c71a8e2caa84160a6323fe3f7e409015644da7a0fbc29b7bc8",
        "config_digest":"50756758daf2925e704f97531b0de7801b077b66548d2212a3515f9fdf9556d2",
        "definition_digest":"5d293f892fd829a9d1c1d2933612bbb4f2d57b4445deefce06436959824cb55b",
        "dna_digest":"2f5e338baa452b2e8779cc9dd9c906ca81c2a4baaf2fd2940d0006295dd14b40",
    },
    "test_reversion":{
        "spec_sha256":"5c9ef5fd81276bbe38ae2d2450f51c1bfa46019c03a36269f8975e0034ca5890",
        "config_digest":"58294b804da8702a02929b2aceb07e900594019c51949dda517cd2c0de1acd0b",
        "definition_digest":"d00ccc44f76785ffec3a17786b3f71303e6d6176809f8d96435c6f8e1c570a1e",
        "dna_digest":"08172a6ce0f65cd2bf8e9e445ddcdbf92d0431040cae4081b61205a4e0518964",
    }
}


def identify_frozen_work235_contracts(work_specs):
    """Recompute proposal/request/draft from *exact* two approved Work235 ASTs.

    "Approved" means frozen identity/definition for contract reuse ONLY;
    the source is explicitly TEST_ONLY and has no independently signed policy.
    """
    from tools.scanner_strategy_f.retrospective_policy import (
        create_retrospective_policy_draft,verify_retrospective_policy_draft,
    )
    from tools.scanner_strategy_e.historical_policy_approval_request import (
        prepare_historical_policy_approval_request,
        verify_historical_policy_approval_request,
    )
    from tools.scanner_strategy_e.historical_research_policy import (
        propose_historical_research_policy, validate_historical_policy_proposal,
    )
    require(type(work_specs) is list and len(work_specs)==2,
            "F_DIAG_FROZEN_WORK235_TWO_REQUIRED")
    strategies={}
    for w in work_specs:
        s=Frozen.restore(w)
        d=s.data
        ident=d.get("strategy_id")
        require(ident in FROZEN and ident not in strategies
                and d.get("strategy_version")=="v1"
                and d.get("scope")=="TEST_ONLY_UNAPPROVED_POLICY"
                and d.get("market")=="fixture"
                and d.get("paper_approval")=="NOT_FOUND"
                and d.get("dna",{}).get("dna",{}).get("provenance",{}).get("kind")
                    =="SYNTHETIC_NOT_AUTHENTICATED",
                "F_DIAG_FROZEN_SOURCE_AUTHORITY_FORBIDDEN")
        expected=FROZEN[ident]
        require(s.sha256==expected["spec_sha256"]
                and d["config_digest"]==expected["config_digest"]
                and d["definition"]["digest"]==expected["definition_digest"]
                and d["dna"]["digest"]==expected["dna_digest"],
                "F_DIAG_WORK235_FROZEN_SHA_MISMATCH")
        strategies[ident]=d
    require(set(strategies)==set(FROZEN),
            "F_DIAG_WORK235_IDENTITY_SET_MISMATCH")
    proposal=propose_historical_research_policy(work_specs)
    request=prepare_historical_policy_approval_request(proposal,work_specs)
    policy=create_retrospective_policy_draft(
        proposal,request,work_specs)
    require(validate_historical_policy_proposal(proposal,work_specs).sha256
                ==proposal["sha256"]
            and verify_historical_policy_approval_request(
                request,proposal,work_specs).sha256==request["sha256"]
            and verify_retrospective_policy_draft(
                policy,proposal,request,work_specs).sha256==policy["sha256"],
            "F_DIAG_POLICY_REVIEW_PARENT_INVALID")
    return {
        "schema":SCHEMA,
        "work235_commit":WORK235_COMMIT,
        "work235_git_blob_sha1":WORK235_BLOB,
        "work235_path":WORK235_PATH,
        "work_specs":work_specs,
        "proposal":proposal,
        "approval_request":request,
        "policy_draft":policy,
        "strategy_identities":{
            sid:{
                "strategy_version":"v1",
                "work235_spec_sha256":FROZEN[sid]["spec_sha256"],
                "work235_config_digest":FROZEN[sid]["config_digest"],
                "definition_digest":FROZEN[sid]["definition_digest"],
                "dna_digest":FROZEN[sid]["dna_digest"],
            } for sid in sorted(FROZEN)},
        "policy_approval_status":"PENDING_INDEPENDENT_OWNER",
        "source_recovery_status":"SEPARATE_OWNER_LOCAL_DIAGNOSTIC_ONLY",
        "original_f2_report_status":"NOT_RECONSTRUCTED",
        "signed_f5_status":"NOT_APPROVED",
        "trading_authority":"NONE",
    }


def load_frozen_work235_contracts(path):
    """Locate actual frozen strategy fixture on an assembled local checkout."""
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and
            p.name=="strategies.json" and
            0<p.stat().st_size<100_000,
            "F_DIAG_ORIGINAL_FROZEN_STRATEGIES_FILE_MISSING")
    specs=json.loads(p.read_text(encoding="utf-8"))
    return identify_frozen_work235_contracts(specs)
