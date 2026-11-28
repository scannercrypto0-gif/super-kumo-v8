import pytest

from tools.atlas_ws_resilience_operator import digest, require_config_snapshot


def test_config_snapshot_accepts_exact_pinned_bytes():
    current = b'{"tree":"C:/atlas","files":[]}'
    require_config_snapshot(current, current, digest(current))


def test_config_snapshot_rejects_competing_edit_before_staging():
    original = b'{"tree":"C:/atlas","files":[]}'
    changed = b'{"tree":"C:/other","files":[]}'
    with pytest.raises(ValueError, match="CONFIG_PIN_CHANGED_BEFORE_STAGE"):
        require_config_snapshot(original, changed, digest(original))

