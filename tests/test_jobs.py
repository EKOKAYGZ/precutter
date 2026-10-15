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

    def fake_render(path, segments, output_path, progress=None):
        output_path.write_bytes(b"video")
        if progress is not None:
            progress(len(segments), len(segments))
        calls.append(segments)

    monkeypatch.setattr(app_module.render, "render", fake_render)

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


def test_preview_audio_extract_and_cache(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path)
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

    for p in (config.WORKSPACE_DIR / "previews").glob("v_t1.m4a"):
        p.unlink(missing_ok=True)


def test_preview_audio_bad_track(monkeypatch, tmp_path):
    _upload_dir(monkeypatch, tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "audio_streams", lambda path, **kw: [{"track": 0}])
    assert client.get("/preview-audio/v.mp4?track=5").status_code == 400
