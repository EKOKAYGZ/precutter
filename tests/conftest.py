"""Shared test isolation."""
import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Launcher env vars from the developer's shell must not leak into tests
    (e.g. PRECUTTER_NO_BROWSER=1 made test_main_reuses_running_instance fail)."""
    for var in ("PRECUTTER_NO_BROWSER", "PRECUTTER_PORT", "PRECUTTER_HOST"):
        monkeypatch.delenv(var, raising=False)
    from precutter import app as app_module

    app_module._stream_count_cache.clear()
    yield
    app_module._stream_count_cache.clear()
