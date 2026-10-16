"""Tests for app settings and storage management."""
import io
import json

import pytest
from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media, settings

client = TestClient(app_module.app)


@pytest.fixture()
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    # Canlı workspace/settings.json import anında config'e sızmış olabilir;
    # testi kod varsayılanlarına sabitle (geçmişteki ENCODER_PREF sızıntısıyla
    # aynı sınıf hata).
    defaults = dict(settings.DEFAULTS)
    monkeypatch.setattr(config, "THRESHOLD_DB", defaults["threshold_db"])
    monkeypatch.setattr(config, "MIN_SILENCE", defaults["min_silence"])
    monkeypatch.setattr(config, "PADDING_PRE", defaults["padding_pre"])
    monkeypatch.setattr(config, "PADDING_POST", defaults["padding_post"])
    monkeypatch.setattr(config, "WHISPER_MODEL", defaults["whisper_model"])
    monkeypatch.setattr(config, "ENCODER_PREF", defaults["encoder"])
    monkeypatch.setattr(config, "QUALITY", defaults["quality"])
    monkeypatch.setattr(config, "OUTPUT_AUDIO", defaults["output_audio"])
    monkeypatch.setattr(
        config, "MAX_UPLOAD_BYTES", int(defaults["max_upload_gb"] * 1024**3))
    monkeypatch.setattr(media, "_ENCODER_CACHE", {})
    return tmp_path


def test_settings_defaults(isolated_settings):
    resp = client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["threshold_db"] == config.THRESHOLD_DB
    assert data["whisper_model"] == "base"
    assert data["encoder"] == "auto"


def test_settings_save_and_apply(isolated_settings):
    resp = client.put("/settings", json={
        "threshold_db": -42, "min_silence": 1.2, "padding_pre": 0.2,
        "padding_post": 0.25, "whisper_model": "small", "encoder": "x264",
        "quality": "small", "output_audio": "separate", "preset": "interview",
        "max_upload_gb": 8,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["threshold_db"] == -42
    assert data["padding_pre"] == 0.2 and data["padding_post"] == 0.25
    assert data["quality"] == "small" and data["output_audio"] == "separate"
    assert data["preset"] == "interview"
    assert config.THRESHOLD_DB == -42
    assert config.PADDING_PRE == 0.2 and config.PADDING_POST == 0.25
    assert config.QUALITY == "small" and config.OUTPUT_AUDIO == "separate"
    assert config.THRESHOLD_DB == -42
    assert config.WHISPER_MODEL == "small"
    assert config.ENCODER_PREF == "x264"
    assert config.MAX_UPLOAD_BYTES == 8 * 1024**3
    # Dosyaya yazildi mi?
    stored = json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8"))
    assert stored["encoder"] == "x264"


def test_settings_rejects_bad_values(isolated_settings):
    assert client.put("/settings", json={"threshold_db": -5}).status_code == 400
    assert client.put("/settings", json={"whisper_model": "huge"}).status_code == 400
    assert client.put("/settings", json={"encoder": "cuda"}).status_code == 400
    assert client.put("/settings", json={"bogus": 1}).status_code == 400


def test_settings_partial_update(isolated_settings):
    resp = client.put("/settings", json={"padding_pre": 0.3})
    assert resp.status_code == 200
    assert resp.json()["padding_pre"] == 0.3
    assert resp.json()["threshold_db"] == config.THRESHOLD_DB


def test_settings_rejects_new_bad_values(isolated_settings):
    assert client.put("/settings", json={"quality": "ultra"}).status_code == 400
    assert client.put("/settings", json={"output_audio": "stereo"}).status_code == 400
    assert client.put("/settings", json={"preset": "movie"}).status_code == 400
    assert client.put("/settings", json={"padding_pre": 5}).status_code == 400
    assert client.put("/settings", json={"ollama_host": "ftp://x"}).status_code == 400
    assert client.put("/settings", json={"ai_model": ""}).status_code == 400
    assert client.put("/settings", json={"ai_threshold": 5}).status_code == 400


def test_settings_ai_fields(isolated_settings):
    resp = client.put("/settings", json={
        "ollama_host": "http://127.0.0.1:11434",
        "ai_model": "qwen3:1.7b",
        "ai_threshold": 40,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ai_model"] == "qwen3:1.7b"
    assert data["ai_threshold"] == 40
    assert config.AI_MODEL == "qwen3:1.7b"
    assert config.AI_THRESHOLD == 40


def test_encoder_pref_forces_x264(monkeypatch):
    monkeypatch.setattr(media, "_ENCODER_CACHE", {})
    monkeypatch.setattr(config, "ENCODER_PREF", "x264")
    assert media.preferred_video_encoder()[1] == "libx264"
    monkeypatch.setattr(config, "ENCODER_PREF", "nvenc")
    media._ENCODER_CACHE.clear()
    assert media.preferred_video_encoder()[1] == "h264_nvenc"


def test_delete_upload(monkeypatch, tmp_path):
    from precutter import app as appmod

    monkeypatch.setattr(appmod.config, "UPLOADS_DIR", tmp_path)
    target = tmp_path / "gone.mp4"
    target.write_bytes(b"0" * 64)
    resp = client.delete("/uploads/gone.mp4")
    assert resp.status_code == 200, resp.text
    assert resp.json()["freed_bytes"] == 64
    assert not target.exists()


def test_delete_upload_missing(monkeypatch, tmp_path):
    from precutter import app as appmod

    monkeypatch.setattr(appmod.config, "UPLOADS_DIR", tmp_path)
    assert client.delete("/uploads/nope.mp4").status_code == 404


def test_storage_clear_cache_only(monkeypatch, tmp_path):
    from precutter import app as appmod

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "keep.mp4").write_bytes(b"0" * 32)
    monkeypatch.setattr(appmod.config, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(appmod.config, "WORKSPACE_DIR", tmp_path)
    previews = tmp_path / "previews"
    previews.mkdir()
    (previews / "x.m4a").write_bytes(b"0" * 16)
    resp = client.post("/storage/clear", json={"target": "cache"})
    assert resp.status_code == 200, resp.text
    assert (uploads / "keep.mp4").exists()
    assert not (previews / "x.m4a").exists()
