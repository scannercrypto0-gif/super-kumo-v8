"""Stage the pinned draft dependencies for the isolated SMA Paper acceptance."""
import argparse
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

from atlas_operator_stage import ROOT, stage

PAPER = "3e7afd10497365dbbfb2a0760bf5f6d0a4591fd1"
SCANNER = "403e247a807b165bc1d6c63991981ce10bc7f6c7"
CENSUS = "35972ffe115cbc1fcde5655d56f1484b19452ca0"


def extract(output, version, *paths):
    archive = subprocess.check_output(
        ["git", "-C", str(ROOT), "archive", "--format=zip", version, *paths]
    )
    with ZipFile(BytesIO(archive)) as bundle:
        bundle.extractall(output)


def stage_package(output):
    stage(output)
    extract(output, PAPER, "src/aql/paper_sim", "src/aql/observation/position_journal.py",
            "src/aql/observation/positions.py")
    extract(output, SCANNER, "tools/scanner_strategy_f/research_e2e_diagnostic.py",
            "tools/strategy_service_offline/common.py")
    extract(output, CENSUS, "tools/first_research_cycle/market-plan.json")
    extract(output, SCANNER, "tools/actual_research_batch_bridge/bridge.py",
            "tools/actual_research_batch_bridge/stage.py")
    # The Scanner module imports the historical reader even for its pure AST entry point.
    extract(output, SCANNER, "research_wp_r0/aql_archive_custody_bridge_v1.py",
            "research_wp_r0/aql_authenticated_historical_admission_v1.py",
            "research_wp_r0/aql_core_backbone_local_v1.py",
            "research_wp_r0/aql_core_chronology_universe_evidence_v1.py",
            "research_wp_r0/aql_core_research_query_seam_v1.py",
            "research_wp_r0/aql_native_price_custody_query_v1.py")
    for name in ("atlas_sma_paper.py", "atlas_live_operator_windows.ps1",
                 "test_atlas_live_operator_recovery.py"):
        shutil.copyfile(ROOT / "tools" / name, output / "tools" / name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    stage_package(parser.parse_args().output)
