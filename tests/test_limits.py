"""Tests for upload limits, upload metadata, and duration guards."""
import io

import pytest
from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media

client = TestClient(app_module.app)


def _upload_file(content: bytes, filename: str = "clip.mp4"):
    return client.post(
        "/upload",
        files={"file": (filename, io.BytesIO(content), "video/mp4")},
    )


def test_upload_rejects_oversize(monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    resp = _upload_file(b"x" * 64)
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_upload_returns_size_and_duration(monkeypatch):
    monkeypatch.setattr(media, "get_duration", lambda path: 12.5)
    resp = _upload_file(b"0" * 100)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["size_bytes"] == 100
    assert data["duration_seconds"] == 12.5
    assert data["original_name"] == "clip.mp4"
    # Temizlik: test yuklemesini sil.
    (config.UPLOADS_DIR / data["filename"]).unlink(missing_ok=True)


def test_upload_rejects_too_long_video(monkeypatch):
    monkeypatch.setattr(media, "get_duration", lambda path: config.MAX_VIDEO_DURATION + 1)
    resp = _upload_file(b"0" * 100)
    assert resp.status_code == 413
    assert "too long" in resp.json()["detail"].lower()


def test_analyze_rejects_too_long_video(monkeypatch, tmp_path):
    from precutter import app as appmod

    fake = tmp_path / "long.mp4"
    fake.write_bytes(b"0" * 16)
    monkeypatch.setattr(appmod.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(media, "get_duration", lambda path: config.MAX_VIDEO_DURATION + 60)
    resp = client.post("/analyze", json={"filename": "long.mp4"})
    assert resp.status_code == 400
    assert "too long" in resp.json()["detail"].lower()


def test_health_reports_limits():
    resp = client.get("/health")
    assert resp.status_code == 200
    limits = resp.json()["limits"]
    assert limits["max_upload_bytes"] == config.MAX_UPLOAD_BYTES
    assert limits["max_video_duration"] == config.MAX_VIDEO_DURATION
    assert ".mp4" in limits["allowed_extensions"]


def test_projects_lists_uploads(monkeypatch, tmp_path):
    from precutter import app as appmod

    (tmp_path / "a.mp4").write_bytes(b"0" * 16)
    (tmp_path / "notes.txt").write_bytes(b"nope")
    monkeypatch.setattr(appmod.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(media, "get_duration", lambda path: 30.0)
    monkeypatch.setattr(media, "audio_streams", lambda path, **kw: [{"track": 0}])
    resp = client.get("/projects")
    assert resp.status_code == 200, resp.text
    names = [p["filename"] for p in resp.json()["projects"]]
    assert "a.mp4" in names
    assert "notes.txt" not in names


def test_media_preview_serves_upload(monkeypatch, tmp_path):
    from precutter import app as appmod

    (tmp_path / "a.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(appmod.config, "UPLOADS_DIR", tmp_path)
    resp = client.get("/media/a.mp4")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"


def test_media_preview_404(monkeypatch, tmp_path):
    from precutter import app as appmod

    monkeypatch.setattr(appmod.config, "UPLOADS_DIR", tmp_path)
    resp = client.get("/media/missing.mp4")
    assert resp.status_code == 404
