"""Tests for the sequential flow: single job-based /analyze, optional subtitles."""
import time

from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media

client = TestClient(app_module.app)


def _upload_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    return tmp_path


def _wait_job(job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in time")


def test_analyze_returns_job_and_completes(monkeypatch, tmp_path):
    """POST /analyze must return {job_id} (not the payload synchronously)."""
    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        media, "audio_streams", lambda path, **kw: [{"track": 0, "channels": 2}])
    monkeypatch.setattr(media, "get_fps", lambda path: 30.0)
    summary = {"new_duration": 8.0, "saved_seconds": 2.0, "saved_percent": 20.0,
               "segment_count": 1, "filler_count": 0,
               "estimated_render_seconds": 4.0}
    monkeypatch.setattr(
        app_module, "_analyze_file",
        lambda path, req, progress=None: (10.0, [[0.0, 8.0]], summary),
    )
    resp = client.post("/analyze", json={"filename": "v.mp4"})
    assert resp.status_code == 200, resp.text
    assert "job_id" in resp.json()
    assert "segments" not in resp.json()
    job = _wait_job(resp.json()["job_id"])
    assert job["status"] == "done", job
    assert job["result"]["segments"] == [[0.0, 8.0]]
    assert job["result"]["transcript"]["available"] is False
    assert "highlights" in job["result"]


def test_analyze_subtitles_only_keeps_segments_but_caches_transcript(
        monkeypatch, tmp_path):
    """make_subtitles without remove_fillers: no cuts, transcript available."""
    from precutter import silence
    from precutter import transcribe as transcribe_mod

    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        media, "audio_streams", lambda path, **kw: [{"track": 0, "channels": 2}])
    monkeypatch.setattr(media, "get_fps", lambda path: 30.0)
    monkeypatch.setattr(silence, "detect_silence", lambda *a, **k: [])
    cached = {
        "language": "en",
        "words": [
            {"text": "um", "start": 1.0, "end": 1.4, "prob": 0.9, "filler": True},
            {"text": "hi", "start": 2.0, "end": 2.4, "prob": 0.9, "filler": False},
        ],
        "fillers": [
            {"text": "um", "start": 1.0, "end": 1.4, "prob": 0.9, "filler": True},
        ],
        "speech": [], "music": [], "silence": [],
        "filler_ratio": 0.5, "duration": 10.0,
    }
    monkeypatch.setattr(transcribe_mod, "load_cache", lambda *a, **k: cached)
    resp = client.post("/analyze", json={"filename": "v.mp4", "make_subtitles": True})
    assert resp.status_code == 200, resp.text
    job = _wait_job(resp.json()["job_id"])
    assert job["status"] == "done", job
    # No filler removal -> whole timeline kept.
    assert job["result"]["segments"] == [[0.0, 10.0]]
    tr = job["result"]["transcript"]
    assert tr["available"] is True
    assert tr["word_count"] == 2
    assert tr["filler_count"] == 1


def test_srt_409_without_transcript(monkeypatch, tmp_path):
    """No cached transcript -> 409 with an actionable message, never Whisper."""
    from precutter import transcribe as transcribe_mod

    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(
        media, "audio_streams", lambda path, **kw: [{"track": 0, "channels": 2}])
    monkeypatch.setattr(transcribe_mod, "load_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        transcribe_mod, "transcribe_file",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    resp = client.post("/srt", json={
        "filename": "v.mp4", "segments": [[0.0, 5.0]], "audio_track": 0})
    assert resp.status_code == 409, resp.text
    assert "nalyz" in resp.json()["detail"]


def test_whisper_model_resolves_from_live_config():
    """Unset model must follow config at call time, not at import time."""
    req = app_module.ProcessRequest(filename="v.mp4")
    assert req.whisper_model is None
    assert app_module._whisper_model(req) == config.WHISPER_MODEL
    req2 = app_module.ProcessRequest(filename="v.mp4", whisper_model="small")
    assert app_module._whisper_model(req2) == "small"


def test_import_links_local_file_without_upload(monkeypatch, tmp_path):
    """Absolute path on disk -> instant link, same payload shape as /upload."""
    _upload_dir(monkeypatch, tmp_path)
    srcdir = tmp_path / "src"
    srcdir.mkdir()
    src = srcdir / "kayit.mp4"
    src.write_bytes(b"0" * 4096)
    resp = client.post("/import", json={"path": str(src)})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["original_name"] == "kayit.mp4"
    assert data["size_bytes"] == 4096
    assert data["filename"].endswith(".mp4")
    stored = tmp_path / data["filename"]
    assert stored.is_file()
    assert stored.read_bytes() == b"0" * 4096
    # Original untouched.
    assert src.is_file()


def test_import_rejects_bad_paths(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path)
    assert client.post("/import", json={"path": "relative/v.mp4"}).status_code == 400
    missing = tmp_path / "yok.mp4"
    assert client.post("/import", json={"path": str(missing)}).status_code == 400
    bad = tmp_path / "not.txt"
    bad.write_bytes(b"x")
    assert client.post("/import", json={"path": str(bad)}).status_code == 400
