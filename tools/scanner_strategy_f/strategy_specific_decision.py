"""Scanner F3 strategy-specific historical decision for original Core query bars.

The work235 strategy *definition and DNA* remain immutable, but the historical
BTCUSDT research-only policy is distinct from TEST_ONLY generator permission.
No strategy is SELECTED from policy + F2 metadata alone. This function binds
actual Core #253 query replay, native #245 receipts and a reproducible
strategy-specific deterministic indicator decision. It issues a Scanner
*decision proposal*, NEVER Core Source ACK or Secretary StrategyApproval.
"""
from __future__ import annotations

from tools.strategy_service_offline.common import Frozen, require
from tools.scanner_strategy_f.source_bound_intake import (
    verify_core_f2_report,
)
from research_wp_r0.aql_core_backbone_local_v1 import query_local
from research_wp_r0.aql_core_dual_query_identity_map_v1 import (
    bind_dual_query_identities,
)
from research_wp_r0.aql_archive_custody_bridge_v1 import digest as core_digest

SCHEMA="aql.scanner-f.historical-original-strategy-decision.v1"
STEP=900_000


def decide_source_bound_strategy(
    source_bound_census,*, warehouse_root, core_f2_report, month,
    warehouse_receipt,native_query_receipt,local_query_receipt,
    identity_map_receipt, strategy_id, strategy_version,
    observed_close_signal,
):
    """A single month/strategy decision, not a canonical strategy approval.

    observed_close_signal must be produced by the separately audited
    strategy-definition/indicator evaluator on exact verified closed Core bars,
    never from a synthetic/mock signal or arbitrary caller boolean. The
    required proof contains that evaluator's independently registered
    version+code+config identity and exact deterministic observation lineage.
    Scanner will not claim a positive SELECTED until Factory/Secretary
    independently check this strategy-specific evidence.
    """
    c=Frozen.restore(source_bound_census)
    d=c.data
    require(d.get("schema")=="aql.scanner-f.historical-source-bound-research-intake.v1"
            and d.get("research_scope")=="RETROSPECTIVE_NON_PIT"
            and d.get("historical_pit")=="NOT_ATTESTED"
            and d.get("selected")==0
            and d.get("attempt_count")==24
            and d.get("secretary_state")=="NOT_ENQUEUED"
            and d.get("trading_authority")=="NONE",
            "F3_STRATEGY_CENSUS_NOT_AUTHORIZED_FOR_RESEARCH")
    records=[Frozen.restore(x).data for x in d["attempts"]]
    matches=[x for x in records if x["month"]==month
             and x["strategy_id"]==strategy_id
             and x["strategy_version"]==strategy_version]
    require(len(matches)==1,"F3_STRATEGY_IDENTITY_OR_MONTH_NOT_IN_CENSUS")
    trial=matches[0]
    require(trial["status"]=="PENDING_RESEARCH_EVALUATION"
            and trial["original_source_sha256"] is not None
            and trial["warehouse_receipt_sha256"] is not None
            and trial["core245_native_query_sha256"] is not None
            and trial["core253_local_query_sha256"] is not None,
            "F3_RETAINED_OR_MISSING_SOURCE_NOT_SELECTABLE")
    require(type(core_f2_report) is dict
            and core_f2_report.get("report_sha256")==d["core_f2_report_sha256"]
            and core_digest({k:v for k,v in core_f2_report.items()
                             if k!="report_sha256"})==core_f2_report["report_sha256"]
            and core_f2_report.get("historical_pit")=="NOT_ATTESTED"
            and core_f2_report.get("strategy_policy_approval")=="NOT_ATTESTED_BY_CORE",
            "F3_SOURCE_F2_PARENT_DRIFT")
    from tools.scanner_strategy_e.historical_core_screening import _sealed
    _sealed(warehouse_receipt,"receipt_sha256",
            "aql.core.local-history-warehouse.v1")
    _sealed(native_query_receipt,"price_query_sha256",
            "aql.core.historical-price-custody-query.v1")
    _sealed(local_query_receipt,"query_sha256",
            "aql.core.local-history-query.v1")
    _sealed(identity_map_receipt,"identity_map_sha256",
            "aql.core.historical-dual-query-identity-map.v1")
    require(warehouse_receipt["receipt_sha256"]==trial["warehouse_receipt_sha256"]
            and warehouse_receipt["source_zip_sha256"]==trial["original_source_sha256"]
            and native_query_receipt["price_query_sha256"]==trial["core245_native_query_sha256"]
            and local_query_receipt["query_sha256"]==trial["core253_local_query_sha256"]
            and identity_map_receipt["identity_map_sha256"]==trial["dual_query_map_sha256"]
            and warehouse_receipt["symbol"]=="BTCUSDT"
            and warehouse_receipt["interval"]=="15m"
            and warehouse_receipt["test_only"] is False
            and warehouse_receipt["availability"]=="RETROSPECTIVE_NON_PIT"
            and warehouse_receipt["coverage"]=="COMPLETE"
            and warehouse_receipt["historical_known_at"]=="NOT_ATTESTED"
            and local_query_receipt["historical_pit"]=="NOT_ATTESTED"
            and native_query_receipt["price_query_sha256"]!=local_query_receipt["query_sha256"]
            and bind_dual_query_identities(native_query_receipt,
                    local_query_receipt,warehouse_receipt)==identity_map_receipt,
            "F3_ORIGINAL_DUAL_QUERY_PARENT_OR_SCOPE")
    replay=query_local(warehouse_root,warehouse_receipt["dataset_id"],
        warehouse_receipt["version"],warehouse_receipt["start_ms"],
        warehouse_receipt["end_exclusive_ms"],
        warehouse_receipt["decision_cutoff_ms"],
        required_source_sha256=trial["original_source_sha256"],
        require_complete=True)
    require(replay==local_query_receipt,"F3_LOCAL_WAREHOUSE_IMMUTABLE_READBACK")
    bars=local_query_receipt["bars"]
    cutoff=warehouse_receipt["decision_cutoff_ms"]
    require(type(bars) is list and len(bars)==trial["expected_bar_count"]
            and len(bars)>0
            and len(bars)<=4096
            and warehouse_receipt["end_exclusive_ms"]<=cutoff
            and all(type(bar["bar_open_ms"]) is int
                and bar["bar_open_ms"]==warehouse_receipt["start_ms"]+i*STEP
                and bar["bar_close_ms"]==bar["bar_open_ms"]+STEP-1
                and bar["bar_close_ms"]<cutoff
                and bar["historical_known_at_ms"] is None
                for i,bar in enumerate(bars)),
            "F3_CLOSED_15M_SOURCE_GRID_PIT_OR_FUTURE")
    require(type(observed_close_signal) is dict and
            set(observed_close_signal)=={
                "schema","strategy_definition_digest","dna_digest",
                "native15m_config_digest","work235_config_digest",
                "core253_query_sha256","core245_query_sha256",
                "evaluated_bar_open_ms","evaluator_code_sha256",
                "evaluator_version","indicator_receipt_sha256",
                "decision","signal_digest",
            } and observed_close_signal["schema"]==
                "aql.scanner-f.external-historical-strategy-signal.v1"
            and observed_close_signal["strategy_definition_digest"]==
                trial["strategy_definition_digest"]
            and observed_close_signal["dna_digest"]==trial["dna_digest"]
            and observed_close_signal["native15m_config_digest"]==
                trial["native15m_config_digest"]
            and observed_close_signal["work235_config_digest"]==
                trial["work235_config_digest"]
            and observed_close_signal["core253_query_sha256"]==
                local_query_receipt["query_sha256"]
            and observed_close_signal["core245_query_sha256"]==
                native_query_receipt["price_query_sha256"]
            and observed_close_signal["decision"] in
                ("REJECTED","UNKNOWN","PROPOSED_RESEARCH_ONLY")
            and type(observed_close_signal["evaluated_bar_open_ms"]) is int
            and observed_close_signal["evaluated_bar_open_ms"]==
                bars[-1]["bar_open_ms"]
            and type(observed_close_signal["evaluator_code_sha256"]) is str
            and len(observed_close_signal["evaluator_code_sha256"])==64
            and type(observed_close_signal["indicator_receipt_sha256"]) is str
            and len(observed_close_signal["indicator_receipt_sha256"])==64
            and core_digest({k:v for k,v in observed_close_signal.items()
                             if k!="signal_digest"})==
                observed_close_signal["signal_digest"],
            "F3_EXTERNAL_EVALUATOR_SIGNAL_SCOPE_OR_SEAL")
    # Do not confuse a caller-created sealed evaluator observation with an
    # independently trusted evaluator trace: these three states are input
    # assertions, never a StrategyApproval or research selection.
    return Frozen.build({
        "schema":SCHEMA,
        "source_bound_census_sha256":c.sha256,
        "strategy_id":strategy_id,
        "strategy_version":strategy_version,
        "month":month,
        "symbol":"BTCUSDT","market":"BINANCE:SPOT:USDT",
        "timeframe":"15m",
        "strategy_definition_digest":trial["strategy_definition_digest"],
        "dna_digest":trial["dna_digest"],
        "native15m_config_digest":trial["native15m_config_digest"],
        "core_f2_report_sha256":d["core_f2_report_sha256"],
        "source_zip_sha256":trial["original_source_sha256"],
        "warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
        "core245_native_query_sha256":native_query_receipt["price_query_sha256"],
        "core253_local_query_sha256":local_query_receipt["query_sha256"],
        "dual_query_map_sha256":identity_map_receipt["identity_map_sha256"],
        "cutoff_ms":cutoff,
        "last_evaluated_open_ms":bars[-1]["bar_open_ms"],
        "external_indicator_receipt_sha256":
            observed_close_signal["indicator_receipt_sha256"],
        "external_signal_digest":observed_close_signal["signal_digest"],
        "signal_observation":observed_close_signal["decision"],
        "decision":"WAIT_INDEPENDENT_EVALUATOR_AND_CORE_SECRETARY_STRATEGY_APPROVAL",
        "selected":False,
        "research_scope":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED",
        "source_ack_sha256":None,
        "strategy_approval_sha256":None,
        "factory_consumer_ack_sha256":None,
        "secretary_state":"NOT_ENQUEUED",
        "factory_lab":"NOT_EVALUATED",
        "holdout":"SEALED",
        "paper":"NOT_ACTIVATED",
        "trading_authority":"NONE",
    }).receipt()
