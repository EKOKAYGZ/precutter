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
        if cmd[0] == config.FFMPEG_BIN:
            return subprocess.CompletedProcess(cmd, 0, "", "mean_volume: -20.0 dB")
        assert cmd[0] == config.FFPROBE_BIN
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_track_loudness_parsed(monkeypatch, tmp_path):
    stderr = "[Parsed_volumedetect_0] mean_volume: -23.4 dB\n[Parsed_volumedetect_0] max_volume: -5.1 dB"

    def fake_run(cmd, **kwargs):
        assert "0:a:1" in cmd
        assert "volumedetect" in cmd
        return subprocess.CompletedProcess(cmd, 0, "", stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0")
    assert media.track_loudness(target, 1) == -23.4


def test_track_loudness_none_when_missing(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("no ffmpeg")

    monkeypatch.setattr(subprocess, "run", fake_run)
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0")
    assert media.track_loudness(target, 0) is None


def test_audio_streams_parsed(monkeypatch, tmp_path):
    _patch_ffprobe(monkeypatch)
    tracks = media.audio_streams(tmp_path / "x.mp4")
    assert [t["track"] for t in tracks] == [0, 1]
    assert tracks[0]["channels"] == 1
    assert tracks[0]["title"] == "Mic"
    assert tracks[1]["channels"] == 2
    assert tracks[1]["codec"] == "aac"
    assert tracks[0]["loudness_db"] == -20.0


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


def test_segment_cmd_maps_all_audio():
    cmd = render._segment_cmd(Path("in.mp4"), 10.0, 5.0, Path("out.mp4"), True)
    assert cmd[cmd.index("-map") + 1] == "0:v"
    assert "0:a" in cmd  # tum ses izleri korunur
    assert "-t" in cmd and "5.000" in cmd
    # Hizli + hassas arama: girdi oncesi ve cikti sonrasi -ss.
    ss_positions = [i for i, a in enumerate(cmd) if a == "-ss"]
    assert len(ss_positions) == 2


def test_segment_cmd_video_only():
    cmd = render._segment_cmd(Path("in.mp4"), 0.0, 1.0, Path("out.mp4"), False)
    assert "0:a" not in cmd
    assert "-c:a" not in cmd


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
