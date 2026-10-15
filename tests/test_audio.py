"""Tests for multi-track / stereo-split audio handling."""
import io
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media, render, silence

client = TestClient(app_module.app)

FFPROBE_TWO_TRACKS = {
    "format": {"duration": "60.0"},
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264"},
        {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 1,
         "tags": {"language": "eng", "title": "Mic"}},
        {"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2,
         "tags": {"language": "eng", "title": "Game+Discord"}},
    ],
}


def _patch_ffprobe(monkeypatch, payload=FFPROBE_TWO_TRACKS):
    def fake_run(cmd, **kwargs):
        assert cmd[0] == config.FFPROBE_BIN
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_audio_streams_parsed(monkeypatch, tmp_path):
    _patch_ffprobe(monkeypatch)
    tracks = media.audio_streams(tmp_path / "x.mp4")
    assert [t["track"] for t in tracks] == [0, 1]
    assert tracks[0]["channels"] == 1
    assert tracks[0]["title"] == "Mic"
    assert tracks[1]["channels"] == 2
    assert tracks[1]["codec"] == "aac"


def test_audio_streams_empty_without_audio(monkeypatch, tmp_path):
    _patch_ffprobe(monkeypatch, {"format": {}, "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264"}]})
    assert media.audio_streams(tmp_path / "x.mp4") == []


def test_detect_silence_maps_track_and_channel(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0")
    silence.detect_silence(target, duration=10.0, audio_track=1, channel=0)
    cmd = seen["cmd"]
    assert "-map" in cmd and "0:a:1" in cmd
    af = cmd[cmd.index("-af") + 1]
    assert af.startswith("pan=mono|c0=c0,silencedetect=")


def test_detect_silence_defaults_unchanged(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0")
    silence.detect_silence(target, duration=10.0)
    cmd = seen["cmd"]
    assert "0:a:0" in cmd
    assert "pan=" not in cmd[cmd.index("-af") + 1]


def test_build_filter_two_tracks():
    filt = render._build_filter([(0.0, 1.0), (2.0, 3.0)], audio_tracks=2)
    assert "[0:a:0]" in filt and "[0:a:1]" in filt
    assert "[outa0]" in filt and "[outa1]" in filt
    assert "[outa]" not in filt.replace("[outa0]", "").replace("[outa1]", "")


def test_build_filter_video_only():
    filt = render._build_filter([(0.0, 1.0)], audio_tracks=0)
    assert "atrim" not in filt
    assert "[outv]" in filt


def test_render_batch_maps_all_tracks(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    render._render_batch(tmp_path / "in.mp4", [(0.0, 1.0)], tmp_path / "out.mp4", 2)
    cmd = seen["cmd"]
    assert "[outa0]" in cmd and "[outa1]" in cmd


def test_check_audio_selection_errors(monkeypatch, tmp_path):
    _patch_ffprobe(monkeypatch)
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0")
    with pytest.raises(media.MediaError, match="track 5"):
        app_module._check_audio_selection(target, 5, None)
    with pytest.raises(media.MediaError, match="channel 3"):
        app_module._check_audio_selection(target, 1, 3)
    # Gecerli secimler sessiz gecmeli.
    app_module._check_audio_selection(target, 1, 1)
    app_module._check_audio_selection(target, 0, None)


def test_streams_endpoint(monkeypatch):
    _patch_ffprobe(monkeypatch)
    monkeypatch.setattr(media, "get_duration", lambda path: 60.0)
    monkeypatch.setattr(
        app_module, "_safe_upload_path", lambda name: Path(name))
    resp = client.post("/streams", json={"filename": "x.mp4"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["audio_streams"]) == 2
    assert data["audio_streams"][1]["channels"] == 2


def test_upload_includes_audio_streams(monkeypatch):
    _patch_ffprobe(monkeypatch)
    monkeypatch.setattr(media, "get_duration", lambda path: 60.0)
    resp = client.post(
        "/upload", files={"file": ("clip.mp4", io.BytesIO(b"0" * 32), "video/mp4")})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["audio_streams"]) == 2
    (config.UPLOADS_DIR / data["filename"]).unlink(missing_ok=True)
