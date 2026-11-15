"""Package H: fail-closed Factory H scientific result -> Core H durable Secretary.

No trading, no independent ACK, no private source read, no duplicate evaluator.
Run in the SHA-verified overlay where Core H and Factory H are pinned.
"""
from __future__ import annotations

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest
from research_wp_r0.aql_core_h_research_secretary_v1 import (
    route_research_result, read_research_result_route,
)

class HBridgeError(ValueError):
    pass


def _need(ok, code):
    if not ok:
        raise HBridgeError("AQL_H_BRIDGE_" + code)


def _sealed(doc, field):
    _need(type(doc) is dict and type(doc.get(field)) is str
          and digest({k: v for k, v in doc.items() if k != field})
          == doc[field], "PARENT_SEAL")


def deliver_research_review_wait(*, secretary_root, packet, factory_report,
                                 factory_h_package, factory_h_result):
    """Verify all existing Factory and Lab parents; persist Core research WAIT.

    The Factory H result's store_status may differ on immutable replay, so the
    immutable package_sha256 (not receipt_sha256) is the scientific parent.
    """
    for doc, field in ((packet, "sha256"),
                       (factory_report, "receipt_sha256"),
                       (factory_h_result, "receipt_sha256"),
                       (factory_h_package, "sha256")):
        _sealed(doc, field)
    _need(packet.get("schema") ==
          "aql.factory.f.f2-recovery-research-input.v2"
          and factory_report.get("schema") ==
          "aql.factory.f.f2-recovery-research-report.v2"
          and factory_h_result.get("schema") ==
          "aql.factory.h.research-package-result.v1"
          and factory_h_package.get("schema") ==
          "aql.factory.h.research-package.v1", "SCHEMA")
    lab=factory_h_package.get("scientific_lab")
    ledger=factory_h_package.get("trade_event_ledger")
    proposal=factory_h_package.get("secretary_research_receipt")
    for doc in (lab,ledger,proposal):
        _sealed(doc, "sha256")
    _need(
        factory_report.get("input_sha256")==packet["sha256"]
        and factory_h_package.get("input_sha256")==packet["sha256"]
        and factory_h_result.get("input_sha256")==packet["sha256"]
        and factory_h_result.get("package_sha256")==factory_h_package["sha256"]
        and factory_h_result.get("scientific_lab_sha256")==lab["sha256"]
        and factory_h_result.get("trade_ledger_sha256")==ledger["sha256"]
        and factory_h_result.get("secretary_receipt_sha256")==proposal["sha256"]
        and lab.get("ledger_sha256")==ledger["sha256"]
        and proposal.get("lab_sha256")==lab["sha256"]
        and proposal.get("result_sha256")==factory_report.get("result_sha256")
        and proposal.get("experiment_sha256")==factory_report.get("experiment_sha256")
        and factory_h_package.get("factory_experiment_sha256")==factory_report.get("experiment_sha256")
        and factory_h_package.get("factory_result_sha256")==factory_report.get("result_sha256")
        and factory_h_result.get("experiment_id")==packet.get("experiment_id")
        and factory_report.get("experiment_id")==packet.get("experiment_id")
        and factory_h_package.get("experiment_id")==packet.get("experiment_id"),
        "CROSS_PARENT_DRIFT")
    _need(
        all(doc.get("trading_authority")=="NONE"
            for doc in (packet, factory_report, factory_h_result,
                        factory_h_package, proposal, lab, ledger))
        and all(proposal.get(k) is None for k in (
            "source_ack_sha256","strategy_approval_sha256",
            "factory_consumer_ack_sha256"))
        and factory_h_package.get("holdout")=="SEALED_UNOPENED"
        and factory_h_result.get("paper")=="NOT_ACTIVATED"
        and factory_h_result.get("f5")=="BLOCKED_EXTERNAL_INPUT"
        and proposal.get("state")=="RESEARCH_RESULT_READY_FOR_REVIEW_NOT_ACK"
        and lab.get("uncertainty",{}).get("economic_claim")=="NOT_ATTESTED",
        "AUTHORITY_OR_ECONOMIC_PROMOTION")
    _need(packet.get("strategy_definitions") is not None
          and packet.get("operator_policy") is not None
          and ledger.get("strategy_digest")==lab.get("strategy_digest")
          and ledger.get("policy_sha256")==lab.get("policy_sha256")
          and proposal.get("policy_sha256")==lab.get("policy_sha256")
          and proposal.get("strategy_definition_sha256")==lab.get("strategy_digest")
          and proposal.get("code_sha256")==packet.get("code_sha256")
          and proposal.get("config_sha256")==packet.get("config_sha256"),
          "STRATEGY_COST_OR_CODE_DRIFT")
    route=route_research_result(
        secretary_root, factory_report,
        strategy_definition_sha256=lab["strategy_digest"],
        strategy_config_sha256=packet["config_sha256"],
        code_sha256=packet["code_sha256"],
        cost_policy_sha256=lab["policy_sha256"],
        lab_report_sha256=lab["sha256"],
    )
    reread=read_research_result_route(secretary_root,packet["experiment_id"])
    _need(route==reread and route.get("state")=="WAIT_RESEARCH_REVIEW"
          and route.get("lab_evaluation_sha256")==lab["sha256"]
          and route.get("strategy_approval_sha256") is None
          and route.get("source_ack_sha256") is None
          and route.get("factory_consumer_ack_sha256") is None
          and route.get("trading_authority")=="NONE", "SECRETARY_READBACK")
    return {
        "schema":"aql.integration.h.secretary-delivery-result.v1",
        "experiment_id":packet["experiment_id"],
        "factory_package_sha256":factory_h_package["sha256"],
        "scientific_lab_sha256":lab["sha256"],
        "secretary_route_sha256":route["receipt_sha256"],
        "status":"WAIT_RESEARCH_REVIEW",
        "economic_status":"ECONOMIC_NOT_ATTESTED",
        "trading_authority":"NONE",
    }
