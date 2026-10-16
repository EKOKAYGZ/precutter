"""Tests for v0.5 features: mix dispositions, bitrate match, mic scoring,
manual segments, SRT, doctor, waveform peaks."""
import io
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media, render, segments
from precutter.transcribe import Word, build_srt

client = TestClient(app_module.app)


def _tracks():
    return [
        {"track": 0, "channels": 2, "codec": "aac", "language": "eng",
         "title": "Game", "loudness_db": -18.0, "max_db": -10.0},
        {"track": 1, "channels": 2, "codec": "aac", "language": "eng",
         "title": "Mic", "loudness_db": -30.0, "max_db": -12.0},
    ]


def test_mic_title_voice_wins():
    tracks = [
        {"track": 0, "title": "Gameplay", "loudness_db": -30.0},
        {"track": 1, "title": "VoiceMeeter", "loudness_db": -18.0},
    ]
    assert media.suggest_mic_track(tracks) == 1


def test_score_track_activity_dyn_range():
    # Same on/off pattern; wider dynamic range scores higher.
    narrow = media.score_track_activity(40, 0.5, 6.0)
    wide = media.score_track_activity(40, 0.5, 24.0)
    assert wide > narrow > 0
    # Backward compatible: no dyn range behaves as before.
    assert media.score_track_activity(40, 0.5) == 1.0
    assert media.score_track_activity(0, 0.5, 30.0) == 0.0


def test_audio_outputs_mix_layout():
    filt, maps, meta = render._audio_outputs(_tracks(), mic_track=1, mode="mix")
    assert filt is not None and "amix" in filt
    assert "volume=1.5" in filt  # mic boosted
    assert maps[0] == "[mixout]"
    assert len(maps) == 3  # mix + 2 originals
    joined = " ".join(maps + meta)
    assert "title=Mix" in joined
    assert meta[meta.index("-disposition:a:0") + 1] == "default"
    assert meta[meta.index("-disposition:a:1") + 1] == "0"


def test_audio_outputs_separate_and_miconly():
    filt, maps, meta = render._audio_outputs(_tracks(), 1, "separate")
    assert maps == ["[ao0]", "[ao1]"]
    assert meta[meta.index("-disposition:a:1") + 1] == "default"
    assert meta[meta.index("-disposition:a:0") + 1] == "0"
    filt, maps, meta = render._audio_outputs(_tracks(), 1, "miconly")
    assert maps == ["[ao0]"]
    assert meta[meta.index("-disposition:a:0") + 1] == "default"


def test_bitrate_match_args(monkeypatch):
    monkeypatch.setattr(media, "_ENCODER_CACHE", {})
    monkeypatch.setattr(config, "ENCODER_PREF", "x264")
    args = media.preferred_video_encoder(quality="match", bitrate_bps=10_000_000)
    assert "-b:v" in args and "10000k" in args
    assert "15000k" in args  # maxrate 1.5x
    args = media.preferred_video_encoder(quality="small")
    assert "26" in args
    args = media.preferred_video_encoder(quality="high")
    assert "20" in args
    media._ENCODER_CACHE.clear()


def test_bitrate_fallback_without_source(monkeypatch):
    monkeypatch.setattr(media, "_ENCODER_CACHE", {})
    monkeypatch.setattr(config, "ENCODER_PREF", "x264")
    args = media.preferred_video_encoder(quality="match", bitrate_bps=None)
    assert "20" in args  # falls back to high
    media._ENCODER_CACHE.clear()


def test_get_video_bitrate(monkeypatch):
    monkeypatch.setattr(media, "_run_ffprobe", lambda path: {
        "format": {}, "streams": [
            {"codec_type": "video", "bit_rate": "8000000"},
            {"codec_type": "audio", "bit_rate": "128000"},
        ]})
    assert media.get_video_bitrate(Path("x.mp4")) == 8000000
    monkeypatch.setattr(media, "_run_ffprobe", lambda path: {
        "format": {"bit_rate": "5000000"}, "streams": []})
    assert media.get_video_bitrate(Path("x.mp4")) == 5000000
    monkeypatch.setattr(media, "_run_ffprobe", lambda path: {"format": {}, "streams": []})
    assert media.get_video_bitrate(Path("x.mp4")) is None


def test_manual_segments_skip_detection(monkeypatch, tmp_path):
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}])
    monkeypatch.setattr(
        __import__("precutter.silence", fromlist=["x"]), "detect_silence",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    req = app_module.ProcessRequest(
        filename="v.mp4", manual_segments=[[1.0, 2.0], [1.5, 3.0], [8.0, 9.0]])
    _, keep, summary = app_module._analyze_file(target, req)
    assert keep == [[1.0, 3.0], [8.0, 9.0]]
    assert summary["segment_count"] == 2


def test_build_srt_remap():
    words = [Word(f"w{i}", 1.0 + i * 0.5, 1.3 + i * 0.5) for i in range(6)]
    # Keep [0,2) and [5,7): w0-w2 stay, the rest fall into cuts.
    srt = build_srt(words, [(0.0, 2.0), (5.0, 7.0)])
    assert "00:00:01,000 --> 00:00:02,300" in srt
    assert "w0 w1 w2" in srt
    # A word later in the second keep shifts left by the cut gap.
    srt = build_srt([Word("late", 5.5, 5.9)], [(0.0, 2.0), (5.0, 7.0)])
    assert "00:00:02,500 --> 00:00:02,900" in srt
    # Words fully inside cuts are dropped.
    srt2 = build_srt([Word("x", 3.0, 3.5)], [(0.0, 2.0), (5.0, 7.0)])
    assert srt2 == ""


def test_srt_endpoint_uses_cache(monkeypatch, tmp_path):
    from precutter import transcribe as transcribe_mod

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}])
    words = [Word("hello", 0.5, 1.0), Word("world", 1.2, 1.6)]
    monkeypatch.setattr(
        transcribe_mod, "load_cache",
        lambda *a, **k: {"language": "en", "words": [
            {"text": "hello", "start": 0.5, "end": 1.0, "prob": 0.9, "filler": False},
            {"text": "world", "start": 1.2, "end": 1.6, "prob": 0.9, "filler": False},
        ], "fillers": [], "speech": [], "music": [], "silence": [],
            "filler_ratio": 0.0, "duration": 10.0})
    monkeypatch.setattr(
        transcribe_mod, "transcribe_file",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must use cache")))
    resp = client.post("/srt", json={
        "filename": "v.mp4", "segments": [[0.0, 5.0]], "audio_track": 0})
    assert resp.status_code == 200, resp.text
    assert "hello world" in resp.text
    assert "-->" in resp.text


def test_doctor_keys():
    resp = client.get("/doctor")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("ffmpeg", "ffprobe", "encoder", "nvenc", "torch", "cuda",
                "whisper", "cpu_count", "free_disk_gb", "ffmpeg_version"):
        assert key in data, key


def test_waveform_peaks_shape(monkeypatch, tmp_path):
    import numpy as _np

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(app_module.config, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}])
    raw = (_np.full(8000 * 4, 1000, dtype=_np.int16)).tobytes()

    import subprocess as _sp

    class _R:
        returncode = 0
        stdout = raw

    monkeypatch.setattr(_sp, "run", lambda *a, **k: _R())
    resp = client.get("/waveform/v.mp4?track=0&peaks=100")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] == 100 and len(data["peaks"]) == 100
    assert all(0.0 <= p <= 1.0 for p in data["peaks"])
    # Second call served from cache (ffmpeg would fail now).
    monkeypatch.setattr(_sp, "run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must use cache")))
    resp2 = client.get("/waveform/v.mp4?track=0&peaks=100")
    assert resp2.status_code == 200


def test_preview_mix_endpoint(monkeypatch, tmp_path):
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(app_module.config, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}, {"track": 1, "channels": 2}])
    import subprocess as _sp

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"fake-mix")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(_sp, "run", fake_run)
    resp = client.get("/preview-mix/v.mp4?tracks=0,1&mic=1")
    assert resp.status_code == 200, resp.text
    assert resp.content == b"fake-mix"
    joined = " ".join(seen["cmd"])
    assert "amix" in joined and "volume=1.5" in joined
    assert client.get("/preview-mix/v.mp4?tracks=9").status_code == 400
