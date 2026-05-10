import pytest

from backend.app.utils.config_utils import required_env


class TestUtil:
    def test_required_env(self):
        val = required_env("TEST")

        assert val == "VALUE"

    def test_missing_required_env(self):
        with pytest.raises(Exception) as exc_info:
            required_env("MISSING")

        assert str(exc_info.value) == "Missing required env: MISSING"