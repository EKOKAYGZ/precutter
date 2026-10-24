"""Regression tests for fix/opencode-issues."""
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media

client = TestClient(app_module.app)


def _upload(monkeypatch, tmp_path, name="v.mp4"):
    uploads = tmp_path / "uploads"
    uploads.mkdir(exist_ok=True)
    monkeypatch.setattr(config, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path)
    target = uploads / name
    target.write_bytes(b"0" * 4096)
    return target


def test_proxy_status_probes_source_once(monkeypatch, tmp_path):
    """Polling /proxy/{name} must not spawn ffprobe on every tick."""
    _upload(monkeypatch, tmp_path)
    calls = []

    def fake_streams(path, **kw):
        calls.append(path)
        return [{"track": 0}, {"track": 1}]

    monkeypatch.setattr(media, "audio_streams", fake_streams)
    for _ in range(5):
        resp = client.get("/proxy/v.mp4")
        assert resp.status_code == 200, resp.text
        assert resp.json()["ready"] is False
    assert len(calls) == 1


def test_delete_upload_removes_proxy_folder(monkeypatch, tmp_path):
    target = _upload(monkeypatch, tmp_path)
    proxy = tmp_path / "previews" / target.stem
    proxy.mkdir(parents=True)
    (proxy / "track0.ogg").write_bytes(b"0" * 2048)
    (proxy / "proxy.mp4").write_bytes(b"0" * 3000)
    resp = client.delete("/uploads/v.mp4")
    assert resp.status_code == 200, resp.text
    assert not proxy.exists()
    assert resp.json()["freed_bytes"] >= 4096 + 2048 + 3000


def test_clear_cache_removes_proxy_folders(monkeypatch, tmp_path):
    target = _upload(monkeypatch, tmp_path)
    previews = tmp_path / "previews"
    proxy = previews / "abc"
    proxy.mkdir(parents=True)
    (proxy / "track0.ogg").write_bytes(b"0" * 2048)
    (previews / "old_t0.m4a").write_bytes(b"0" * 100)
    import precutter.transcribe as transcribe_mod
    monkeypatch.setattr(transcribe_mod, "cache_dir", lambda: tmp_path / "nocache")
    resp = client.post("/storage/clear", json={"target": "cache"})
    assert resp.status_code == 200, resp.text
    assert not proxy.exists()
    assert not (previews / "old_t0.m4a").exists()
    assert target.exists()  # cache clear keeps uploads
    assert resp.json()["freed_bytes"] >= 2148


def test_connection_reset_noise_is_swallowed():
    seen = []
    handler = app_module._quiet_connection_reset_handler(
        lambda loop, ctx: seen.append(ctx))
    loop = asyncio.new_event_loop()
    try:
        handler(loop, {"message": "x", "exception": ConnectionResetError(10054)})
        handler(loop, {"message": "x", "exception": ConnectionAbortedError()})
        assert seen == []
        handler(loop, {"message": "real", "exception": ValueError("boom")})
        assert len(seen) == 1 and seen[0]["message"] == "real"
    finally:
        loop.close()


def test_proxy_poll_is_bound_to_its_file():
    """Switching files must not attach the old file's proxies to the new one."""
    js = (Path(app_module.__file__).parent / "static" / "app.js").read_text(
        encoding="utf-8")
    assert "async function pollProxyJob(jobId, name)" in js
    assert "await pollProxyJob(job_id, name);" in js
    assert js.count("uploadedName !== name") >= 4
