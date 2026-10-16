"""End-to-end multi-track render check with a real generated fixture.

Generates a 30 s mp4 with 2 audio tracks (game = constant tone, mic = tone
with silent gaps), analyzes the mic track, renders 10+ segments, and verifies
with ffprobe: 2 audio tracks kept, metadata preserved, all streams start at
0 and video/audio durations match within 30 ms.

Skipped when ffmpeg/ffprobe are not available (set PRECUTTER_TEST_FFMPEG /
PRECUTTER_TEST_FFPROBE to override binary paths).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from precutter import config, media, render, segments, silence


def _bins():
    ff = os.environ.get("PRECUTTER_TEST_FFMPEG") or shutil.which("ffmpeg")
    fp = os.environ.get("PRECUTTER_TEST_FFPROBE") or shutil.which("ffprobe")
    return ff, fp


needs_tools = pytest.mark.skipif(
    not all(_bins()), reason="ffmpeg/ffprobe not available"
)


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"FAILED: {cmd}\n{r.stderr[-1500:]}"
    return r


def _probe(ffprobe, path):
    r = _run([ffprobe, "-v", "error", "-print_format", "json",
              "-show_format", "-show_streams", str(path)])
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def two_track_src(tmp_path_factory):
    ff, fp = _bins()
    if not (ff and fp):
        pytest.skip("ffmpeg/ffprobe not available")
    d = tmp_path_factory.mktemp("twotrack")
    src = d / "two_track.mp4"
    gate = "volume=volume='if(lt(mod(t\\,1.5)\\,0.75)\\,1\\,0)':eval=frame"
    _run([ff, "-hide_banner", "-y",
          "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=30",
          "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
          "-f", "lavfi", "-i", "sine=frequency=880:duration=30",
          "-filter_complex",
          f"[1:a]volume=0.5,aformat=channel_layouts=stereo[game];"
          f"[2:a]{gate},volume=0.5,aformat=channel_layouts=stereo[mic]",
          "-map", "0:v", "-map", "[game]", "-map", "[mic]",
          "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
          "-metadata:s:a:0", "language=eng",
          "-metadata:s:a:1", "language=eng",
          "-shortest", str(src)])
    return src


@pytest.fixture()
def use_bins(monkeypatch):
    ff, fp = _bins()
    monkeypatch.setattr(config, "FFMPEG_BIN", ff)
    monkeypatch.setattr(config, "FFPROBE_BIN", fp)
    media._ENCODER_CACHE.clear()
    yield
    media._ENCODER_CACHE.clear()


@needs_tools
def test_fixture_has_two_audio_tracks(two_track_src, use_bins):
    ff, fp = _bins()
    streams = _probe(fp, two_track_src)["streams"]
    kinds = [s["codec_type"] for s in streams]
    assert kinds == ["video", "audio", "audio"]
    assert all(s["channels"] == 2 for s in streams if s["codec_type"] == "audio")


@needs_tools
def test_analyze_detects_mic_gaps(two_track_src, use_bins):
    dur = media.get_duration(two_track_src)
    assert dur == pytest.approx(30.0, abs=0.1)
    sils = silence.detect_silence(two_track_src, -35, 0.5, dur, audio_track=1)
    assert len(sils) >= 10, f"expected mic gaps, got {sils}"
    keep = segments.build_segments(sils, dur, padding_pre=0.05, padding_post=0.05)
    assert len(keep) >= 10


@needs_tools
def test_render_keeps_both_tracks_in_sync(two_track_src, use_bins, tmp_path):
    ff, fp = _bins()
    dur = media.get_duration(two_track_src)
    sils = silence.detect_silence(two_track_src, -35, 0.5, dur, audio_track=1)
    keep = segments.build_segments(sils, dur, padding_pre=0.05, padding_post=0.05)
    assert len(keep) >= 10

    out = tmp_path / "out.mp4"
    progress_calls = []
    render.render(two_track_src, keep, out, output_audio="separate",
                  progress=lambda d, t: progress_calls.append((d, t)))
    assert progress_calls and progress_calls[-1][0] == progress_calls[-1][1]

    info = _probe(fp, out)
    streams = info["streams"]
    assert [s["codec_type"] for s in streams] == ["video", "audio", "audio"]
    audios = [s for s in streams if s["codec_type"] == "audio"]
    assert [(s.get("tags") or {}).get("language") for s in audios] == ["eng", "eng"]

    starts = [float(s.get("start_time", 0.0)) for s in streams]
    assert all(s < 0.005 for s in starts), starts

    durs = {s["codec_type"] + str(i): float(s["duration"])
            for i, s in enumerate(streams)}
    video_dur = float([s for s in streams if s["codec_type"] == "video"][0]["duration"])
    for a in audios:
        assert abs(float(a["duration"]) - video_dur) < 0.030, (
            video_dur, a["duration"])


@pytest.fixture(scope="module")
def dense_src(tmp_path_factory):
    """30 s, 2 tracks; mic has ~100 short gaps (0.15 s silence every 0.3 s)."""
    ff, fp = _bins()
    if not (ff and fp):
        pytest.skip("ffmpeg/ffprobe not available")
    d = tmp_path_factory.mktemp("dense")
    src = d / "dense.mp4"
    gate = "volume=volume='if(lt(mod(t\\,0.3)\\,0.15)\\,1\\,0)':eval=frame"
    _run([ff, "-hide_banner", "-y",
          "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=30",
          "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
          "-f", "lavfi", "-i", "sine=frequency=880:duration=30",
          "-filter_complex",
          f"[1:a]volume=0.5,aformat=channel_layouts=stereo[game];"
          f"[2:a]{gate},volume=0.5,aformat=channel_layouts=stereo[mic]",
          "-map", "0:v", "-map", "[game]", "-map", "[mic]",
          "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
          "-metadata:s:a:0", "language=eng",
          "-metadata:s:a:1", "language=eng",
          "-shortest", str(src)])
    return src


@needs_tools
def test_render_dense_segments_duration_accuracy(dense_src, use_bins, tmp_path):
    ff, fp = _bins()
    dur = media.get_duration(dense_src)
    sils = silence.detect_silence(dense_src, -35, 0.1, dur, audio_track=1)
    keep = segments.build_segments(sils, dur, padding_pre=0.02, padding_post=0.02,
                                    min_keep=0.05, merge_gap=0.0)
    keep = segments.snap_to_frames(keep, 30.0, dur)
    assert len(keep) >= 50, f"expected a dense cut list, got {len(keep)}"
    expected = sum(e - s for s, e in keep)

    out = tmp_path / "out_dense.mp4"
    render.render(dense_src, keep, out, output_audio="separate")

    info = _probe(fp, out)
    streams = info["streams"]
    assert [s["codec_type"] for s in streams] == ["video", "audio", "audio"]
    audios = [s for s in streams if s["codec_type"] == "audio"]

    starts = [float(s.get("start_time", 0.0)) for s in streams]
    assert all(s < 0.005 for s in starts), starts

    video_dur = float(
        [s for s in streams if s["codec_type"] == "video"][0]["duration"])
    assert abs(video_dur - expected) < 1 / 30 + 0.005, (video_dur, expected)
    for a in audios:
        assert abs(float(a["duration"]) - video_dur) < 0.020, (
            video_dur, a["duration"])


def _decode_rms(ff, path, stream, t0=0.0, dur=1.0):
    import numpy as np

    r = subprocess.run(
        [ff, "-hide_banner", "-v", "error", "-ss", str(t0), "-i", str(path),
         "-map", stream, "-t", str(dur), "-f", "s16le", "-ac", "1",
         "-ar", "48000", "-"], capture_output=True, check=True)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(float)
    return float((x ** 2).mean() ** 0.5) if len(x) else 0.0


@pytest.fixture(scope="module")
def obs_src(tmp_path_factory):
    """OBS-like: quiet constant game tone + loud mic tone with gaps."""
    ff, fp = _bins()
    if not (ff and fp):
        pytest.skip("ffmpeg/ffprobe not available")
    d = tmp_path_factory.mktemp("obs")
    src = d / "obs_like.mp4"
    gate = "volume=volume='if(lt(mod(t\\,1.5)\\,1.05)\\,1\\,0)':eval=frame"
    _run([ff, "-hide_banner", "-y",
          "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=30",
          "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
          "-f", "lavfi", "-i", "sine=frequency=880:duration=30",
          "-filter_complex",
          f"[1:a]volume=0.02,aformat=channel_layouts=stereo[game];"
          f"[2:a]{gate},volume=0.5,aformat=channel_layouts=stereo[mic]",
          "-map", "0:v", "-map", "[game]", "-map", "[mic]",
          "-c:v", "libx264", "-preset", "ultrafast", "-b:v", "1500k",
          "-c:a", "aac", "-b:a", "128k",
          "-metadata:s:a:0", "name=Game", "-metadata:s:a:0", "language=eng",
          "-metadata:s:a:1", "name=Microphone", "-metadata:s:a:1", "language=eng",
          "-shortest", str(src)])
    return src


@needs_tools
def test_obs_mix_default_carries_mic(obs_src, use_bins, tmp_path):
    ff, fp = _bins()
    tracks = media.audio_streams(obs_src)
    assert len(tracks) == 2
    sugg = media.suggest_mic_with_confidence(obs_src, tracks)
    assert sugg["track"] == 1, sugg  # quiet game must not win

    dur = media.get_duration(obs_src)
    sils = silence.detect_silence(obs_src, -35, 0.3, dur, audio_track=1)
    assert len(sils) >= 10
    keep = segments.build_segments(sils, dur, padding_pre=0.05,
                                    padding_post=0.05, min_keep=0.1,
                                    merge_gap=0.0)
    keep = segments.snap_to_frames(keep, 30.0, dur)
    assert len(keep) >= 10

    out = tmp_path / "out_obs.mp4"
    render.render(obs_src, keep, out, mic_track=1)  # default mix mode
    info = _probe(fp, out)
    streams = info["streams"]
    assert [s["codec_type"] for s in streams] == ["video", "audio", "audio", "audio"]
    audios = [s for s in streams if s["codec_type"] == "audio"]
    assert [a.get("disposition", {}).get("default", 0) for a in audios][0] == 1
    assert [(a.get("tags") or {}).get("language") for a in audios] == ["eng"] * 3

    mix_level = _decode_rms(ff, out, "0:a:0", 0.1, 0.8)
    game_level = _decode_rms(ff, out, "0:a:1", 0.1, 0.8)
    assert mix_level > 2 * game_level, (mix_level, game_level)

    src_vbr = media.get_video_bitrate(obs_src)
    out_vbr = media.get_video_bitrate(out)
    assert src_vbr and out_vbr
    assert out_vbr <= 1.5 * src_vbr, (src_vbr, out_vbr)

    for mode, expect in (("separate", 2), ("miconly", 1)):
        o = tmp_path / f"out_{mode}.mp4"
        render.render(obs_src, keep[:4], o, mic_track=1, output_audio=mode)
        kinds = [s["codec_type"] for s in _probe(fp, o)["streams"]]
        assert kinds == ["video"] + ["audio"] * expect, (mode, kinds)
