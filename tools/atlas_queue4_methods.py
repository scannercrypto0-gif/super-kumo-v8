"""Produce or replay the native Queue 4 synthetic trial-methods receipt."""

import argparse
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from research_wp_r0.aql_factory_e_research_results_store_v1 import digest
from research_wp_r0.aql_queue4_methods_v1 import context, record_methods, replay_methods, require
from research_wp_r0.durable_journal import DurableTrialJournal
from research_wp_r0.evaluation import OpportunityOutcome, evaluate_paired, Resolution
from research_wp_r0.owner_checkpoints import export_checkpoint, verify_owner_checkpoint
from tools.atlas_queue2_dev import produce as produce_dev, readback as read_dev


def verify(directory):
    read_dev(directory / "dev")
    evidence = json.loads((directory / "dev/evidence.json").read_text(encoding="utf-8"))
    receipt = json.loads((directory / "methods.json").read_text(encoding="utf-8"))
    return replay_methods(evidence["paired_package"], directory / "methods", receipt)


def produce(directory):
    directory.mkdir(parents=True, exist_ok=False)
    produce_dev(directory / "dev")
    read_dev(directory / "dev")
    package = json.loads((directory / "dev/evidence.json").read_text(encoding="utf-8"))["paired_package"]
    receipt = record_methods(package, directory / "methods")
    second = record_methods(package, directory / "repeat")
    require(receipt == second, "QUEUE4_NONDETERMINISTIC_REPLAY")
    (directory / "methods.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                            encoding="utf-8")
    verify(directory)
    family, manifest, pairs = context(package)
    rejected = {}

    def reject(name, operation):
        try:
            operation()
        except (ValueError, OSError) as error:
            rejected[name] = str(error)
        else:
            raise ValueError("QUEUE4_ACCEPTED_" + name)

    reject("missing_denominator", lambda: evaluate_paired(
        pairs[:-1], block_length=1, replicates=100, seed=4,
        minimum_paired=2, temporal_manifest=manifest))
    reject("lookahead", lambda: replace(
        manifest.ordered[0], baseline_feature_available_at=manifest.ordered[0].baseline_horizon_end_at))
    reject("nonfinite", lambda: OpportunityOutcome("x", "x", Resolution.KNOWN, float("nan"), 0))
    bad = deepcopy(package)
    bad["cohort_receipt"]["source_zip_sha256"] = "0" * 64
    bad["sha256"] = digest({k: v for k, v in bad.items() if k != "sha256"})
    reject("wrong_source", lambda: replay_methods(bad, directory / "methods", receipt))
    contaminated = deepcopy(package)
    contaminated["splits"]["holdout_status"] = "OPEN"
    contaminated["sha256"] = digest({k: v for k, v in contaminated.items() if k != "sha256"})
    reject("contaminated_holdout", lambda: context(contaminated))
    with DurableTrialJournal(directory / "methods/trials.jsonl", family) as journal:
        reject("ineligible_selection", lambda: journal.select(
            family.candidate_ids[0], at=manifest.ordered[-1].baseline_horizon_end_at,
            event_id="forbidden-selection"))
        reject("false_external_anchor", lambda: verify_owner_checkpoint(
            journal, export_checkpoint(journal), independently_trusted=False))
    with TemporaryDirectory() as scratch:
        clone = Path(scratch) / "methods"
        shutil.copytree(directory / "methods", clone)
        path = clone / "trials.jsonl"
        content = path.read_bytes()
        path.write_bytes(content.splitlines(keepends=True)[0])
        reject("rollback", lambda: replay_methods(package, clone, receipt))
        path.write_bytes(content[:-3])
        reject("truncated_write", lambda: replay_methods(package, clone, receipt))
        path.write_bytes(content.replace(b"INELIGIBLE", b"INELIGIBLX"))
        reject("corruption", lambda: replay_methods(package, clone, receipt))
    verify(directory)
    negatives = {"rejections": rejected, "count": len(rejected), "receipt_sha256": receipt["sha256"]}
    (directory / "negatives.json").write_text(json.dumps(negatives, indent=2, sort_keys=True) + "\n",
                                             encoding="utf-8")
    return {"receipt_sha256": receipt["sha256"], "negatives": len(rejected),
            "source_class": "SYNTHETIC_FIXTURE_ONLY", "trading_authority": "NONE"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()

    def forbid_network(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            raise RuntimeError("QUEUE4_NETWORK_FORBIDDEN")

    sys.addaudithook(forbid_network)
    print(json.dumps(verify(args.directory) if args.readback else produce(args.directory),
                     sort_keys=True))
