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


def test_preferred_video_encoder_nvenc(monkeypatch):
    media._ENCODER_CACHE.clear()
    # Kayıtlı ayarlar (workspace/settings.json) global config'e sızar; bu test
    # "auto" algılamayı ölçtüğü için tercihi açıkça sabitliyoruz.
    monkeypatch.setattr(config, "ENCODER_PREF", "auto")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, " V..... h264_nvenc  NVIDIA NVENC", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert media.preferred_video_encoder()[:2] == ["-c:v", "h264_nvenc"]
    assert media.encoder_name() == "nvenc"
    media._ENCODER_CACHE.clear()


def test_preferred_video_encoder_fallback_x264(monkeypatch):
    media._ENCODER_CACHE.clear()
    monkeypatch.setattr(config, "ENCODER_PREF", "auto")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, "no nvenc here", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert media.preferred_video_encoder()[:2] == ["-c:v", "libx264"]
    assert media.encoder_name() == "x264"
    media._ENCODER_CACHE.clear()


def test_segment_cmd_uses_preferred_encoder(monkeypatch, tmp_path):
    monkeypatch.setattr(render, "preferred_video_encoder",
                        lambda: ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"])
    cmd = render._segment_cmd(tmp_path / "i.mp4", 1.0, 2.0, tmp_path / "o.mp4", True)
    assert "h264_nvenc" in cmd
    assert "libx264" not in cmd


def test_suggest_mic_track():
    assert media.suggest_mic_track([]) is None
    assert media.suggest_mic_track([{"track": 0}]) == 0
    # Title wins.
    tracks = [
        {"track": 0, "title": "Game", "loudness_db": -30.0},
        {"track": 1, "title": "Mic", "loudness_db": -12.0},
    ]
    assert media.suggest_mic_track(tracks) == 1
    tracks = [
        {"track": 0, "title": "Desktop", "loudness_db": -18.0},
        {"track": 1, "title": "Mikrofon", "loudness_db": -28.0},
    ]
    assert media.suggest_mic_track(tracks) == 1
    # Else lowest mean loudness (sparse speech vs constant game tone).
    tracks = [
        {"track": 0, "title": "", "loudness_db": -20.0},
        {"track": 1, "title": "", "loudness_db": -30.0},
    ]
    assert media.suggest_mic_track(tracks) == 1
    # Ambiguous levels -> None.
    tracks = [
        {"track": 0, "title": "", "loudness_db": -20.0},
        {"track": 1, "title": "", "loudness_db": -20.4},
    ]
    assert media.suggest_mic_track(tracks) is None
    # No measurements -> None.
    assert media.suggest_mic_track([{"track": 0}, {"track": 1}]) is None


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
    cmd = render._segment_cmd(Path("in.mp4"), 10.0, 5.0, Path("out.mkv"), True)
    assert cmd[cmd.index("-map") + 1] == "0:v:0"
    assert "0:a?" in cmd  # tum ses izleri korunur
    # Kesim sadece trim filtreleriyle; cikti -ss/-t yok.
    assert cmd.count("-ss") == 1
    assert "-t" not in cmd
    assert "trim=start=1.999800:end=6.999900" in " ".join(cmd)
    # PCM ara urun: birlestirme ornek-hassas olur, AAC kaymasi olmaz.
    assert "pcm_s16le" in cmd


def test_segment_cmd_video_only():
    cmd = render._segment_cmd(Path("in.mp4"), 0.0, 1.0, Path("out.mkv"), False)
    assert "pcm_s16le" not in cmd
    assert "0:v:0" in cmd


def test_concat_cmd_keeps_all_tracks(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    render._concat_parts([Path("a.mkv"), Path("b.mkv")], tmp_path / "out.mkv")
    cmd = seen["cmd"]
    map_idx = cmd.index("-map")
    assert cmd[map_idx + 1] == "0"
    assert "-map_metadata" in cmd
    assert cmd[cmd.index("-c") + 1] == "copy"


def test_final_mux_cmd_metadata():
    tracks = [
        {"language": "eng", "title": "Game"},
        {"language": "tur", "title": "Mic"},
    ]
    # Default mix mode: [mixed default] + originals.
    cmd = render._final_mux_cmd(Path("j.mkv"), Path("o.mp4"), tracks, True,
                                mic_track=1, mode="mix")
    assert cmd[cmd.index("-map") + 1] == "0:v:0"
    assert "[mixout]" in cmd
    assert "[ao1]" in cmd and "[ao2]" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "aac" in cmd
    assert "language=tur" in cmd and "title=Mic" in cmd
    assert "title=Mix" in cmd
    assert "-disposition:a:0" in cmd
    assert cmd[cmd.index("-disposition:a:0") + 1] == "default"
    assert cmd[cmd.index("-disposition:a:1") + 1] == "0"
    # Separate mode: originals only, mic is default.
    cmd = render._final_mux_cmd(Path("j.mkv"), Path("o.mp4"), tracks, True,
                                mic_track=1, mode="separate")
    assert "[mixout]" not in " ".join(cmd)
    assert cmd[cmd.index("-disposition:a:1") + 1] == "default"
    assert cmd[cmd.index("-disposition:a:0") + 1] == "0"
    # Mic-only mode: single default track.
    cmd = render._final_mux_cmd(Path("j.mkv"), Path("o.mp4"), tracks, True,
                                mic_track=1, mode="miconly")
    assert cmd.count("-map") == 2  # video + one audio
    assert cmd[cmd.index("-disposition:a:0") + 1] == "default"


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
    assert "suggested_mic" in data


def test_streams_suggests_titled_mic(monkeypatch):
    payload = {
        "format": {"duration": "60.0"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264"},
            {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2,
             "tags": {"language": "eng", "title": "Game"}},
            {"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2,
             "tags": {"language": "eng", "title": "Mic"}},
        ],
    }
    _patch_ffprobe(monkeypatch, payload)
    monkeypatch.setattr(media, "get_duration", lambda path: 60.0)
    monkeypatch.setattr(
        app_module, "_safe_upload_path", lambda name: Path(name))
    resp = client.post("/streams", json={"filename": "x.mp4"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["suggested_mic"] == 1


def test_upload_includes_audio_streams(monkeypatch):
    _patch_ffprobe(monkeypatch)
    monkeypatch.setattr(media, "get_duration", lambda path: 60.0)
    resp = client.post(
        "/upload", files={"file": ("clip.mp4", io.BytesIO(b"0" * 32), "video/mp4")})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["audio_streams"]) == 2
    (config.UPLOADS_DIR / data["filename"]).unlink(missing_ok=True)


def test_analyze_subtracts_fillers(monkeypatch, tmp_path):
    """remove_fillers=True cuts filler ranges out of keep-segments."""
    from precutter import transcribe as transcribe_mod

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}],
    )
    monkeypatch.setattr(
        silence, "detect_silence", lambda *a, **k: [])
    filler_words = [
        transcribe_mod.Word(text="um", start=2.0, end=2.5, filler=True),
        transcribe_mod.Word(text="hi", start=3.0, end=3.5, filler=False),
    ]

    class FakeTranscript:
        words = filler_words
        fillers = [filler_words[0]]

    monkeypatch.setattr(
        transcribe_mod, "transcribe_file",
        lambda *a, **k: FakeTranscript(),
    )

    req = app_module.ProcessRequest(filename="v.mp4")
    assert req.remove_fillers is False
    _, keep_plain, summary_plain = app_module._analyze_file(target, req)
    assert keep_plain == [[0.0, 10.0]]
    assert summary_plain["filler_count"] == 0

    req_fill = app_module.ProcessRequest(filename="v.mp4", remove_fillers=True)
    _, keep_cut, summary_cut = app_module._analyze_file(target, req_fill)
    assert keep_cut == [[0.0, 1.95], [2.55, 10.0]]
    assert summary_cut["filler_count"] == 1
    assert summary_cut["new_duration"] < summary_plain["new_duration"]


def test_analyze_uses_cached_transcript(monkeypatch, tmp_path):
    """Cache hit: transcribe_file must not run; estimate still works."""
    from precutter import transcribe as transcribe_mod

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}],
    )
    monkeypatch.setattr(silence, "detect_silence", lambda *a, **k: [])
    cached = {
        "language": "en",
        "words": [
            {"text": "um", "start": 1.0, "end": 1.4, "prob": 0.9, "filler": True},
        ],
        "fillers": [
            {"text": "um", "start": 1.0, "end": 1.4, "prob": 0.9, "filler": True},
        ],
        "speech": [], "music": [], "silence": [],
        "filler_ratio": 1.0, "duration": 10.0,
    }
    monkeypatch.setattr(
        transcribe_mod, "load_cache", lambda *a, **k: cached)
    monkeypatch.setattr(
        transcribe_mod, "transcribe_file",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("whisper must not run")),
    )
    req = app_module.ProcessRequest(filename="v.mp4", remove_fillers=True)
    _, keep, summary = app_module._analyze_file(target, req)
    assert keep == [[0.0, 0.95], [1.45, 10.0]]
    assert summary["filler_count"] == 1
    assert summary["estimated_render_seconds"] > 0


def test_analyze_filler_needs_whisper(monkeypatch, tmp_path):
    """No cache + no Whisper -> clear error, not a crash."""
    from precutter import transcribe as transcribe_mod

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}],
    )
    monkeypatch.setattr(silence, "detect_silence", lambda *a, **k: [])
    monkeypatch.setattr(transcribe_mod, "load_cache", lambda *a, **k: None)

    def _missing(*a, **k):
        raise media.MediaError(
            "faster-whisper is not installed. Run: pip install faster-whisper")

    monkeypatch.setattr(transcribe_mod, "transcribe_file", _missing)
    req = app_module.ProcessRequest(filename="v.mp4", remove_fillers=True)
    try:
        app_module._analyze_file(target, req)
    except media.MediaError as exc:
        assert "Whisper" in str(exc) or "whisper" in str(exc).lower()
    else:
        raise AssertionError("expected MediaError")


def test_score_track_activity():
    assert media.score_track_activity(0, 0.5) == 0.0
    assert media.score_track_activity(3, 0.5) == 0.0
    assert media.score_track_activity(40, 0.0) == 0.0
    assert media.score_track_activity(40, 1.0) == 0.0
    assert media.score_track_activity(40, 0.04) == 0.0
    good = media.score_track_activity(40, 0.5)
    assert 0.5 < good <= 1.0


def _two_tracks():
    return [
        {"track": 0, "title": "", "channels": 2,
         "loudness_db": -18.0, "max_db": -10.0},
        {"track": 1, "title": "", "channels": 2,
         "loudness_db": -30.0, "max_db": -12.0},
    ]


def test_suggest_mic_by_activity(monkeypatch, tmp_path):
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)

    def fake_activity(path, track, *a, **k):
        if track == 0:
            return {"silence_ratio": 0.0, "transitions": 0, "window": 120.0}
        return {"silence_ratio": 0.4, "transitions": 40, "window": 120.0}

    monkeypatch.setattr(media, "track_silence_activity", fake_activity)
    res = media.suggest_mic_with_confidence(target, _two_tracks())
    assert res["track"] == 1
    assert res["confidence"] > 0.5


def test_suggest_mic_fallback_last_track(monkeypatch, tmp_path):
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(
        media, "track_silence_activity",
        lambda path, track, *a, **k: {
            "silence_ratio": 0.0, "transitions": 0, "window": 120.0})
    ambiguous = [
        {"track": 0, "title": "", "channels": 2,
         "loudness_db": -20.0, "max_db": -10.0},
        {"track": 1, "title": "", "channels": 2,
         "loudness_db": -20.4, "max_db": -10.0},
    ]
    res = media.suggest_mic_with_confidence(target, ambiguous)
    assert res == {"track": 1, "confidence": 0.3}


def test_suggest_mic_single_and_empty(tmp_path):
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    assert media.suggest_mic_with_confidence(
        target, [{"track": 0}]) == {"track": 0, "confidence": 0.5}
    assert media.suggest_mic_with_confidence(target, []) is None


def test_check_free_space_ok(monkeypatch, tmp_path):
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0" * 1024)
    monkeypatch.setattr(media, "get_duration", lambda path: 100.0)
    render.check_free_space(
        src, [(0.0, 10.0)], tmp_path / "o.mp4", [{"channels": 2}])


def test_check_free_space_raises(monkeypatch, tmp_path):
    import shutil as _shutil

    src = tmp_path / "v.mp4"
    src.write_bytes(b"0" * 1024)
    monkeypatch.setattr(media, "get_duration", lambda path: 100.0)

    class _Usage:
        free = 1024 * 1024  # 1 MB

    monkeypatch.setattr(_shutil, "disk_usage", lambda path: _Usage())
    try:
        render.check_free_space(
            src, [(0.0, 10.0)], tmp_path / "o.mp4", [{"channels": 2}])
    except media.MediaError as exc:
        assert "disk space" in str(exc).lower()
    else:
        raise AssertionError("expected MediaError")


def test_segment_cmd_exact_audio_length(tmp_path):
    cmd = render._segment_cmd(Path("in.mp4"), 10.0, 5.0, Path("out.mkv"), True)
    joined = " ".join(cmd)
    # Bounds are relative to the input-seek point (10 - 8 = 2.0).
    assert "atrim=start=1.999800:end=6.999900" in joined
    assert "trim=start=1.999800:end=6.999900" in joined
    # No output-side -ss/-t: cutting is done purely with trim filters.
    assert cmd.count("-ss") == 1
    assert "-t" not in cmd
