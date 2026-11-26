"""The real G1 pipeline exposes an opt-in post-ACK seam, default disabled."""
import inspect

from aql.pipeline import run_pipeline
from aql.lanes import JournalConsumer


def test_pipeline_explicit_optional_seam_default_off():
    parameter = inspect.signature(run_pipeline).parameters["after_persisted"]
    assert parameter.default is None


def test_consumer_seam_explicit_optional_default_off():
    parameter = inspect.signature(JournalConsumer).parameters["after_persisted"]
    assert parameter.default is None
