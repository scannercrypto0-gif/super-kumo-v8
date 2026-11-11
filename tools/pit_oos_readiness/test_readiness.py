"""Only the new joined delta. No replay of accepted market or G2 suites."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.pit_oos_readiness import readiness as r
from tools.pit_oos_readiness import proof


@pytest.fixture
def prepared(tmp_path):
    protocol, packet = r.configuration()
    journal, plan, freeze, witness = r.prepare(tmp_path, protocol)
    bar, _, _ = next(r.opportunities(protocol, packet))
    return protocol, journal, plan, freeze, witness, bar, r.publication(protocol, bar, freeze)


@pytest.mark.parametrize("attack,reason", [
    ("rights", "RIGHTS_OR_TERMS"),
    ("unknown_first_release", "FIRST_RELEASE_FIELDS"),
    ("future_known_at", "FIRST_RELEASE_CHRONOLOGY"),
    ("late_receive", "FIRST_RELEASE_CHRONOLOGY"),
    ("correction", "CORRECTION_QUARANTINE"),
    ("source_swap", "FOREIGN_OR_CHANGED_SOURCE"),
    ("historical_pit_label", "FOREIGN_OR_REAL_SOURCE"),
    ("changed_bar", "FOREIGN_OR_CHANGED_SOURCE"),
    ("bad_grid", "FINAL_GRID"),
    ("late_witness", "LATE_WITNESS"),
    ("wrong_witness", "WITNESS_SCOPE"),
    ("signature_tamper", "MOCK_RECEIPT_INTEGRITY"),
    ("embargo", "OUTSIDE_ELIGIBLE_SPLIT"),
    ("holdout_peek", "OOS_SEALED_NO_PEEK"),
])
def test_admission_rejects_before_journal_write(tmp_path, prepared, attack, reason):
    protocol, journal, plan, freeze, witness, bar, receipt = prepared
    pub = deepcopy(receipt["payload"])
    attestation = deepcopy(witness["payload"])
    if attack == "rights":
        pub["rights_sha256"] = "0" * 64
    elif attack == "unknown_first_release":
        del pub["first_known_at_ms"]
    elif attack == "future_known_at":
        pub["first_known_at_ms"] += r.STEP
    elif attack == "late_receive":
        pub["received_at_ms"] += r.STEP
    elif attack == "correction":
        pub.update(release_version=2, correction_of="original")
    elif attack == "source_swap":
        pub["source_sha256"] = "0" * 64
    elif attack == "historical_pit_label":
        protocol["source"]["evidence_class"] = "RETROSPECTIVE_NON_PIT"
        pub["source_sha256"] = r.digest(protocol["source"])
        attestation["protocol_sha256"] = r.digest(protocol)
    elif attack == "changed_bar":
        bar.close = 99.5
    elif attack in ("bad_grid", "embargo", "holdout_peek"):
        slot = {"bad_grid": r.STEP + 1, "embargo": protocol["times"]["train_end_ms"],
                "holdout_peek": protocol["times"]["oos_start_ms"]}[attack]
        bar = r.market_bar(slot, dict(open=100, high=101, low=99, close=100))
        pub = r.publication(protocol, bar, freeze)["payload"]
    elif attack == "late_witness":
        attestation["witnessed_at_ms"] = protocol["times"]["first_eligible_open_ms"]
    elif attack == "wrong_witness":
        attestation["freeze_sha256"] = "0" * 64
    witness = r.mock_receipt("witness", attestation)
    receipt = r.mock_receipt("publisher", pub)
    if attack == "signature_tamper":
        receipt["mac"] = "0" * 64
    with pytest.raises(ValueError, match=reason):
        r.admit(tmp_path, protocol, journal, plan, freeze, witness, bar, receipt)
    assert not journal.replay(symbol="BTC-USD", interval="15m")


def test_immutable_trial_budget_and_plan(tmp_path, prepared):
    protocol, _, plan, _, witness, _, _ = prepared
    with pytest.raises(ValueError):
        r.verify_research_plan(plan + b" ", witness["payload"]["plan_sha256"])
    protocol["candidates"].append({"candidate_id": "late-candidate"})
    with pytest.raises(ValueError, match="IMMUTABLE_CONFLICT"):
        r.prepare(tmp_path, protocol)


def test_duplicate_and_revision(tmp_path, prepared):
    protocol, journal, plan, freeze, witness, bar, receipt = prepared
    args = (tmp_path, protocol, journal, plan, freeze, witness)
    first = r.admit(*args, bar, receipt)
    assert first == r.admit(*args, bar, receipt)
    bar.close = 99.5
    with pytest.raises(ValueError, match="IMMUTABLE_CONFLICT"):
        r.admit(*args, bar, r.publication(protocol, bar, freeze))
    assert len(journal.replay(symbol="BTC-USD", interval="15m")) == 1


@pytest.fixture(scope="module")
def native_report():
    from research_wp_r0.aql_factory_h_scientific_lab_v1 import evaluate_execution_exit_comparison
    _, packet = r.configuration()
    return evaluate_execution_exit_comparison(packet), packet


@pytest.mark.parametrize("attack,reason", [
    ("swapped_input", "REPORT_AUTHORITY"),
    ("fake_fill", "REPORT_AUTHORITY"),
    ("fake_pit", "REPORT_AUTHORITY"),
    ("open_holdout", "REPORT_AUTHORITY"),
    ("promotion", "REPORT_AUTHORITY"),
    ("seal_break", "REPORT_SEAL"),
    ("missing_variant", "MODEL_POPULATION"),
    ("duplicate_cost", "COST_ONCE"),
    ("unknown_profit", "UNKNOWN_PROFIT"),
    ("no_fill_profit", "NONFILL_PROFIT"),
])
def test_factory_negative_contract(native_report, attack, reason):
    original, packet = native_report
    report = deepcopy(original)
    r.validate_report(original, packet)
    if attack == "swapped_input":
        report["input_sha256"] = "0" * 64
    elif attack == "fake_fill":
        report["actual_fills"] = 1
    elif attack == "fake_pit":
        report["historical_pit"] = "ATTESTED"
    elif attack == "open_holdout":
        report["holdout"] = "OPEN"
    elif attack == "promotion":
        report["winner"] = "C"
    elif attack == "missing_variant":
        report["outcomes"].pop()
    elif attack == "duplicate_cost":
        row = next(row for row in report["outcomes"] if row["status"] == "MODEL_ONLY")
        row["legs"].append(deepcopy(row["legs"][0]))
    elif attack == "unknown_profit":
        next(row for row in report["outcomes"] if row["status"] == "UNKNOWN_FILL")["net_return"] = "1"
    elif attack == "no_fill_profit":
        next(row for row in report["outcomes"] if row["status"] == "NONFILL")["net_return"] = "1"
    if attack != "seal_break":
        report["sha256"] = r.digest({k: v for k, v in report.items() if k != "sha256"})
    else:
        report["winner"] = "C"
    with pytest.raises(ValueError, match=reason):
        r.validate_report(report, packet)


def test_unowned_store_is_untouched(tmp_path):
    db = tmp_path / "journal.sqlite"
    db.write_bytes(b"not our journal")
    with pytest.raises(ValueError, match="UNOWNED_CUSTODY"):
        r.run(tmp_path)
    assert db.read_bytes() == b"not our journal"


def test_foreign_holdout_index_stops_before_native_payload_read(tmp_path, prepared):
    protocol, journal, _, _, _, _, _ = prepared
    holdout = r.market_bar(protocol["times"]["oos_start_ms"], dict(open=100, high=101, low=99, close=100))
    journal.commit(holdout)
    with r.patch.object(r.DurableJournal, "replay", side_effect=AssertionError("payload read")):
        with pytest.raises(ValueError, match="FOREIGN_OR_HOLDOUT_CUSTODY"):
            r.run(tmp_path)


def test_interrupted_native_ack_is_not_invented(tmp_path, prepared):
    protocol, journal, plan, freeze, witness, bar, receipt = prepared
    args = (tmp_path, protocol, journal, plan, freeze, witness, bar, receipt)
    with r.patch("aql.journal.durable_journal.post_commit_receipt", side_effect=ValueError("interrupted ACK")):
        with pytest.raises(ValueError, match="interrupted ACK"):
            r.admit(*args)
    with pytest.raises(ValueError, match="POST_COMMIT_CUTOFF_RECEIPT_REQUIRED"):
        r.admit(*args)


def test_two_processes_and_hard_crash(tmp_path):
    def execute(name, *args):
        return subprocess.run([sys.executable, "-B", "-m", "tools.pit_oos_readiness.readiness",
                               str(tmp_path / name), *args], capture_output=True, timeout=90)

    for name in ("first", "second"):
        result = execute(name)
        assert result.returncode == 0, result.stderr.decode()
    assert execute("recovery", "--crash").returncode == 73
    assert len(list((tmp_path / "recovery").glob("publication-*.json"))) == 1
    resumed = execute("recovery")
    assert resumed.returncode == 0, resumed.stderr.decode()
    baseline = (tmp_path / "first/decision.json").read_bytes()
    assert baseline == (tmp_path / "second/decision.json").read_bytes() == (tmp_path / "recovery/decision.json").read_bytes()
    receipt = json.loads(baseline)
    assert receipt["opportunity_census"] == {"ENTRY": 5, "NO_SIGNAL": 43, "REJECTED": 1, "UNKNOWN": 1}
    assert receipt["trial_census"] == {"FAILED": 1, "SELECTED": 1, "UNSCANNED": 1}
    assert receipt["outcome_census"] == {"MODEL_ONLY": 48, "NONFILL": 3, "UNKNOWN_FILL": 12, "UNKNOWN_INTRABAR_STOP_TARGET": 9}
    assert receipt["cohort_prices_opened"] == 0 and receipt["collection"] == "NOT_ACTIVATED"


@pytest.fixture(scope="module")
def signed_fixture(tmp_path_factory):
    """Ephemeral test signers. The runtime verifier takes public keys only."""
    import base64
    from research_wp_r0.frozen_research_plan import commit_research_plan

    root = tmp_path_factory.mktemp("signers")
    keys = {}
    executable = proof.openssl_path()
    for role in proof.ROLES:
        path = root / f"{role}.pem"
        subprocess.run([executable, "genpkey", "-algorithm", "ED25519", "-out", str(path)], check=True)
        keys[role] = subprocess.check_output([executable, "pkey", "-in", str(path), "-pubout"]).decode().replace("\r\n", "\n")

    def sign(role, payload):
        message = root / "message"
        message.write_bytes(proof.canonical(dict(role=role, payload=payload)))
        signature = subprocess.check_output([executable, "pkeyutl", "-sign", "-rawin", "-inkey",
                                             str(root / f"{role}.pem"), "-in", str(message)])
        return dict(role=role, payload=payload, signature=base64.b64encode(signature).decode())

    times = dict(first_open_ms=r.STEP, train_end_ms=3*r.STEP, validation_start_ms=3*r.STEP+r.EMBARGO,
                 validation_end_ms=5*r.STEP+r.EMBARGO, oos_start_ms=5*r.STEP+2*r.EMBARGO,
                 oos_end_ms=7*r.STEP+2*r.EMBARGO, step_ms=r.STEP)
    plan, plan_sha = commit_research_plan("fixture-proof", [("fixture", "1"*64)],
        protocol_digest="2"*64, dataset_digest="3"*64, split_digest=r.digest(times), metrics=["net"],
        selection_rule={"mode": "fixed"}, cost_model={"mode": "mock"}, baseline_digest="4"*64)
    owner = dict(**times, decision="APPROVED_RESEARCH_ONLY", authority="NONE", plan_sha256=plan_sha,
                 source_sha256="3"*64, rights_sha256="5"*64, rights_use="PERSONAL_NONCOMMERCIAL_RESEARCH",
                 terms_version="fixture", terms_from_ms=0, terms_until_ms=times["oos_end_ms"]+r.STEP,
                 approval_ms=3000, custody_sha256="6"*64, slot_limit=8, byte_limit=4096, spend_ceiling=0)
    release = dict(source_sha256=owner["source_sha256"], rights_sha256=owner["rights_sha256"],
                   open_ms=r.STEP, close_ms=2*r.STEP-1, first_available_ms=2*r.STEP,
                   version=1, correction_of=None, content_sha256="7"*64)
    return keys, plan, owner, release, sign


@pytest.mark.parametrize("case,reason", [
    ("valid", None),
    ("untrusted_keys", "EXTERNAL_TRUST_PIN"),
    ("duplicate_roles", "INDEPENDENT_ROLE_KEYS"),
    ("wrong_signature", "SIGNATURE_INVALID_PUBLISHER"),
    ("late_prefreeze", "PROSPECTIVE_CHRONOLOGY"),
    ("correction", "CORRECTION_QUARANTINE"),
    ("fake_ack", "CUSTODY_ACK_BINDING"),
])
def test_future_signed_proof_contract(signed_fixture, case, reason):
    keys, plan, owner, release, sign = deepcopy(signed_fixture)
    bundle = {"owner": sign("owner", owner)}
    bundle["witness"] = sign("witness", dict(owner_sha256=r.digest(bundle["owner"]),
        plan_sha256=owner["plan_sha256"], witnessed_ms=2*r.STEP if case == "late_prefreeze" else 4000))
    if case == "correction":
        release.update(version=2, correction_of="prior")
    bundle["publisher"] = sign("publisher", release)
    bundle["receiver"] = sign("receiver", dict(release_sha256=r.digest(bundle["publisher"]), received_ms=2*r.STEP+1))
    bundle["custodian"] = sign("custodian", dict(received_sha256=r.digest(bundle["receiver"]),
        content_sha256=release["content_sha256"], custody_sha256=owner["custody_sha256"],
        committed_ms=2*r.STEP+2, immutable_ack=case != "fake_ack", holdout="SEALED_UNOPENED"))
    if case == "wrong_signature":
        release["content_sha256"] = "8"*64
    if case == "duplicate_roles":
        keys["witness"] = keys["owner"]
    pin = "0"*64 if case == "untrusted_keys" else r.digest(keys)
    if reason:
        with pytest.raises(ValueError, match=reason):
            proof.verify_bundle(bundle, keys, pin, plan)
    else:
        result = proof.verify_bundle(bundle, keys, pin, plan)
        assert result["status"] == "SIGNED_PROOF_CONTRACT_VERIFIED_RELATIVE_TO_SUPPLIED_PINS"
        assert result["real_science"] == "REAL_PIT_OOS_BLOCKED" and result["collection"] == "NOT_ACTIVATED"
