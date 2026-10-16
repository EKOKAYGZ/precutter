"""Tests for the launcher helpers: free port, existing instance, env flags."""
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import uvicorn

from precutter import app as app_module


def _bound_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock


def test_port_free_detects_busy_port():
    busy = _bound_socket()
    try:
        port = busy.getsockname()[1]
        assert app_module._port_free(port) is False
    finally:
        busy.close()


def test_pick_port_moves_past_busy_port():
    busy = _bound_socket()
    try:
        port = busy.getsockname()[1]
        chosen = app_module._pick_port(port)
        assert port < chosen <= port + 20
        assert app_module._port_free(chosen) is True
    finally:
        busy.close()


def test_pick_port_returns_preferred_when_free():
    probe = _bound_socket()
    port = probe.getsockname()[1]
    probe.close()
    assert app_module._pick_port(port) == port


def test_looks_like_precutter_against_real_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            body = b"<!doctype html><title>PreCutter</title>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the test output clean
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        assert app_module._looks_like_precutter(port) is True
    finally:
        server.shutdown()
        server.server_close()

    # Some other website on that port is not "our" server.
    other = _bound_socket()
    try:
        assert app_module._looks_like_precutter(other.getsockname()[1]) is False
    finally:
        other.close()


def test_env_flag(monkeypatch):
    monkeypatch.setenv("PRECUTTER_TEST_FLAG", "1")
    assert app_module._env_flag("PRECUTTER_TEST_FLAG") is True
    monkeypatch.setenv("PRECUTTER_TEST_FLAG", "off")
    assert app_module._env_flag("PRECUTTER_TEST_FLAG") is False
    monkeypatch.delenv("PRECUTTER_TEST_FLAG", raising=False)
    assert app_module._env_flag("PRECUTTER_TEST_FLAG") is False


def test_main_reuses_running_instance(monkeypatch):
    """Already running -> open the browser instead of a second server."""
    monkeypatch.delenv("PRECUTTER_PORT", raising=False)
    monkeypatch.setattr(app_module, "_port_free", lambda port: False)
    monkeypatch.setattr(app_module, "_looks_like_precutter", lambda port: True)
    monkeypatch.setattr(app_module, "_open_browser_when_ready",
                        lambda *a, **k: pytest.fail("must not wait for a new server"))
    opened = []
    monkeypatch.setattr(app_module.webbrowser, "open", lambda url: opened.append(url))
    started = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(k))

    app_module.main()

    assert started == []
    assert opened == ["http://127.0.0.1:8000"]


def test_main_starts_server_without_browser(monkeypatch):
    monkeypatch.delenv("PRECUTTER_PORT", raising=False)
    monkeypatch.setenv("PRECUTTER_HOST", "127.0.0.1")
    monkeypatch.setenv("PRECUTTER_NO_BROWSER", "1")
    monkeypatch.setattr(app_module, "_port_free", lambda port: True)
    monkeypatch.setattr(app_module, "_open_browser_when_ready",
                        lambda *a, **k: pytest.fail("browser disabled via env"))
    started = {}
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: started.update(kw))

    app_module.main()

    assert started["host"] == "127.0.0.1"
    assert started["port"] == 8000
    assert started["reload"] is False


def test_main_falls_back_to_next_free_port(monkeypatch):
    monkeypatch.delenv("PRECUTTER_PORT", raising=False)
    monkeypatch.setenv("PRECUTTER_NO_BROWSER", "1")
    monkeypatch.setattr(app_module, "_port_free", lambda port: False)
    monkeypatch.setattr(app_module, "_looks_like_precutter", lambda port: False)
    monkeypatch.setattr(app_module, "_pick_port", lambda port, tries=20: 8007)
    started = {}
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: started.update(kw))

    app_module.main()

    assert started["port"] == 8007
