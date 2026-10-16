"""Tests for background render jobs and audio preview audition."""
import subprocess
import time
from pathlib import Path

from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media

client = TestClient(app_module.app)


def _upload_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    return tmp_path


def test_render_job_lifecycle(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)

    summary = {"new_duration": 5.0, "saved_seconds": 5.0, "saved_percent": 50.0,
               "segment_count": 2, "estimated_render_seconds": 4.0}
    monkeypatch.setattr(
        app_module, "_analyze_file",
        lambda path, req: (10.0, [[0.0, 2.0], [5.0, 8.0]], summary),
    )

    calls = []

    def fake_render(path, segments, output_path, progress=None,
                    mic_track=0, output_audio=None):
        output_path.write_bytes(b"video")
        if progress is not None:
            progress(len(segments), len(segments))
        calls.append(segments)

    monkeypatch.setattr(app_module.render, "render", fake_render)
    monkeypatch.setattr(
        media, "audio_streams", lambda path, **kw: [{"track": 0}, {"track": 1}])

    resp = client.post("/render", json={"filename": "v.mp4"})
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    for _ in range(100):
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert job["done"] == 2 and job["total"] == 2
    assert job["download_url"].startswith("/download/")
    assert job["output_audio_tracks"] == 2
    assert calls and len(calls[0]) == 2
    (config.OUTPUTS_DIR / job["filename"]).unlink(missing_ok=True)


def test_render_job_reports_analysis_error(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)

    def boom(path, req):
        raise media.MediaError("Nothing to keep after analysis.")

    monkeypatch.setattr(app_module, "_analyze_file", boom)
    job_id = client.post("/render", json={"filename": "v.mp4"}).json()["job_id"]
    for _ in range(100):
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] == "error":
            break
        time.sleep(0.05)
    assert job["status"] == "error"
    assert "Nothing to keep" in job["error"]


def test_job_not_found():
    assert client.get("/jobs/nope").status_code == 404


def test_queued_job_reports_blocker():
    """Slotu tutan iş, bekleyenin /jobs çıktısında görünür."""
    with app_module._heavy_slot("holder1", "render"):
        with app_module._jobs_lock:
            app_module._jobs["waiter1"] = {
                "status": "working", "stage": "queued", "done": 0,
                "total": None, "created": time.time()}
        try:
            data = client.get("/jobs/waiter1").json()
            assert data["blocked_by"] == {"job_id": "holder1", "kind": "render"}
        finally:
            with app_module._jobs_lock:
                app_module._jobs.pop("waiter1", None)
    assert app_module._HEAVY_HOLDER is None


def test_preview_audio_extract_and_cache(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}, {"track": 1, "channels": 1}],
    )

    runs = []

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"fake-audio")
        runs.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    resp = client.get("/preview-audio/v.mp4?track=1")
    assert resp.status_code == 200, resp.text
    assert resp.content == b"fake-audio"
    # Ikinci cagri onbellekten gelmeli (ffmpeg bir kez calisti).
    resp2 = client.get("/preview-audio/v.mp4?track=1")
    assert resp2.status_code == 200
    assert len(runs) == 1
    assert (tmp_path / "previews" / "v_t1_mono.m4a").exists()


def test_preview_audio_channel_solo(monkeypatch, tmp_path):
    from precutter import app as appmod

    _upload_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}],
    )

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"fake-audio")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    resp = client.get("/preview-audio/v.mp4?track=0&channel=1")
    assert resp.status_code == 200, resp.text
    cmd = seen["cmd"]
    assert "-ac" in cmd and "1" in cmd
    assert any("pan=mono" in a for a in cmd)
    assert (tmp_path / "previews" / "v_t0_ch1_mono.m4a").exists()


def test_preview_audio_bad_channel(monkeypatch, tmp_path):
    from precutter import app as appmod

    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 1}],
    )
    assert client.get("/preview-audio/v.mp4?track=0&channel=1").status_code == 400


def test_preview_audio_bad_track(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "audio_streams", lambda path, **kw: [{"track": 0}])
    assert client.get("/preview-audio/v.mp4?track=5").status_code == 400
