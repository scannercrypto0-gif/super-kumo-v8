from pathlib import Path
import tempfile

from tools.realtime_market_feed.atlas_integration import _warehouse_evidence_class


def test_evidence_class_is_synthetic_only_for_temporary_warehouse():
    temporary_root=Path(tempfile.gettempdir())/"aql-generated-fixture"
    assert _warehouse_evidence_class(temporary_root)=="GENERATED_SYNTHETIC_FIXTURE"
    repository_root=Path(__file__).resolve().parents[2]
    assert _warehouse_evidence_class(repository_root)=="NATIVE_ARCHIVE_READBACK"
