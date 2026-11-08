"""ATLAS Integration-only isolated Scanner import seam (no original source).

The Scanner #277 frozen identity constants are needed by H2's manual strategy.
F3 retrospective-policy imports bring old unpublished scanner_strategy_b at
module import time even though that legacy F3 diagnostic is NOT invoked in H2.

Move those exact source imports to their only F3 call sites, *without* forging
scanner_strategy_b or editing Scanner PR/source checkout. All existing functions
retain their runtime dependencies if called. The transformed isolated code is
hashed and reported as a distinct Integration compatibility seam, never as an
unaltered Scanner #277 blob. Fail closed on anchor/schema/source drift.
"""
from __future__ import annotations
import hashlib
from pathlib import Path


class ImportSeamBlocked(ValueError):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _move(root, rel, imports, function, marker):
    path = Path(root)/rel
    if not path.is_file() or path.is_symlink():
        raise ImportSeamBlocked("SCANNER_IMPORT_SEAM_PINNED_SOURCE_MISSING")
    before = path.read_bytes()
    try:
        code = before.decode("utf-8")
    except UnicodeError:
        raise ImportSeamBlocked("SCANNER_IMPORT_SEAM_SOURCE_ENCODING") from None
    if code.count(imports) != 1 or code.count(function) != 1 or code.count(marker) != 1:
        raise ImportSeamBlocked("SCANNER_IMPORT_SEAM_SOURCE_CONTRACT_DRIFT")
    # Move rather than elide imports. F3 called in its original F3 context
    # still imports the same dependencies and fails closed if unavailable.
    code = code.replace(imports, "", 1)
    code = code.replace(marker, "    "+imports.replace("\n","\n    ").rstrip()+"\n"+marker, 1)
    if imports in code[:code.index(function)]:
        raise ImportSeamBlocked("SCANNER_IMPORT_SEAM_TOPLEVEL_STILL_PRESENT")
    after = code.encode("utf-8")
    if after == before:
        raise ImportSeamBlocked("SCANNER_IMPORT_SEAM_NO_CHANGE")
    path.write_bytes(after)
    return {"path":rel,"original_sha256":_sha(before),
            "isolated_seam_sha256":_sha(after)}


def apply_import_seam(root):
    frozen_imports = (
        "from tools.scanner_strategy_e.historical_research_policy import (\n"
        "    propose_historical_research_policy, validate_historical_policy_proposal,\n"
        ")\n"
        "from tools.scanner_strategy_e.historical_policy_approval_request import (\n"
        "    prepare_historical_policy_approval_request,\n"
        "    verify_historical_policy_approval_request,\n"
        ")\n"
        "from tools.scanner_strategy_f.retrospective_policy import (\n"
        "    create_retrospective_policy_draft,verify_retrospective_policy_draft,\n"
        ")\n"
    )
    a=_move(
        root,"tools/scanner_strategy_f/frozen_diagnostic_contracts.py",
        frozen_imports,
        "def identify_frozen_work235_contracts(work_specs):",
        "    proposal=propose_historical_research_policy(work_specs)",
    )
    b=_move(
        root,"tools/scanner_strategy_f/research_e2e_diagnostic.py",
        "from tools.scanner_strategy_f.retrospective_policy import verify_retrospective_policy_draft\n",
        "def diagnostic_original_cohort(",
        "    frozen=verify_retrospective_policy_draft(",
    )
    return {"schema":"aql.integration.h2.pinned-scanner-import-seam.v2",
            "only_isolated_overlay":True,
            "missing_scanner_strategy_b_not_fabricated":True,
            "changed_modules":[a,b]}
