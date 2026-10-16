"""v0.3 sound events: spike detection, highlight building, scoring."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from precutter import app as app_module
from precutter import config, media
from precutter import events as events_mod


def _curve(base_db, bursts, n=200, step=0.1):
    times = [round(i * step, 3) for i in range(n)]
    curve = [base_db] * n
    for at, peak in bursts:
        idx = int(round(at / step))
        for k in range(-2, 3):
            if 0 <= idx + k < n:
                curve[idx + k] = max(curve[idx + k], peak - abs(k) * 3)
    return times, curve


def test_detect_spikes_finds_burst():
    times, curve = _curve(-30.0, [(5.0, -8.0)])
    spikes = events_mod.detect_spikes(times, curve)
    assert len(spikes) == 1
    assert abs(spikes[0]["time"] - 5.0) < 0.2
    assert spikes[0]["delta_db"] >= 20
    assert spikes[0]["peak_db"] >= -9


def test_detect_spikes_ignores_quiet_and_floor():
    times, curve = _curve(-30.0, [(5.0, -25.0)])  # only 5 dB over baseline
    assert events_mod.detect_spikes(times, curve) == []
    times2, curve2 = _curve(-70.0, [(5.0, -55.0)])  # loud-ish but under floor
    assert events_mod.detect_spikes(times2, curve2) == []


def test_detect_spikes_keeps_loudest_within_gap():
    times, curve = _curve(-30.0, [(5.0, -10.0), (5.4, -6.0)])
    spikes = events_mod.detect_spikes(times, curve)
    assert len(spikes) == 1
    assert spikes[0]["peak_db"] >= -7


def test_build_highlights_padding_and_merge():
    spikes = [
        {"time": 5.0, "peak_db": -8.0, "delta_db": 22.0},
        {"time": 5.6, "peak_db": -7.0, "delta_db": 23.0},
        {"time": 40.0, "peak_db": -9.0, "delta_db": 16.0},
    ]
    out = events_mod.build_highlights(spikes, 60.0)
    assert len(out) == 2
    first = min(out, key=lambda h: h["start"])
    assert first["start"] == 3.0  # 5.0 - pre_pad
    assert first["end"] == 6.6  # merged with 5.6 + post_pad
    assert first["score"] >= 70  # 40 + 30 (delta) + 5 (peak)
    assert any(r.startswith("spike+") for r in first["reasons"])


def test_score_highlight_table():
    loud = {"time": 1.0, "peak_db": -5.0, "delta_db": 22.0}
    score, reasons = events_mod.score_highlight(loud, 2.0, has_speech=True)
    assert score == 90  # 40 + 30 + 10 + 10
    assert "has-speech" in reasons
    musical = {"time": 1.0, "peak_db": -5.0, "delta_db": 22.0}
    score_m, reasons_m = events_mod.score_highlight(musical, 2.0, has_music=True)
    assert score_m == score - 25  # -15 music, no +10 speech
    assert "over-music" in reasons_m
    mild = {"time": 1.0, "peak_db": -20.0, "delta_db": 12.5}
    score_low, _ = events_mod.score_highlight(mild, 2.0)
    assert score_low == 50  # 40 + 10


def _bins():
    ff = os.environ.get("PRECUTTER_TEST_FFMPEG") or shutil.which("ffmpeg")
    return ff


needs_ffmpeg = pytest.mark.skipif(
    not _bins(), reason="ffmpeg not available")


@needs_ffmpeg
def test_analyze_events_on_generated_wav(tmp_path, monkeypatch):
    ff = _bins()
    monkeypatch.setattr(config, "FFMPEG_BIN", ff)
    wav = tmp_path / "burst.wav"
    # 10 s tone, quiet except a loud 1 s burst at t=5.
    r = subprocess.run(
        [ff, "-hide_banner", "-y", "-f", "lavfi",
         "-i", "sine=frequency=880:duration=10",
         "-af", "volume='if(between(t,5,6),0.9,0.05)':eval=frame",
         "-c:a", "pcm_s16le", str(wav)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-1000:]
    out = events_mod.analyze_events(wav, 0, 10.0)
    assert len(out) >= 1
    best = out[0]
    assert best["start"] <= 3.5 and best["end"] >= 5.5
    assert best["score"] >= 70
    assert best["delta_db"] >= 12


def test_analyze_ai_cut_falls_back_without_ollama(monkeypatch, tmp_path):
    """ai_cut + Ollama down -> heuristic scores, analysis still completes."""
    from precutter import transcribe as transcribe_mod
    from precutter import score as score_mod

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}])
    monkeypatch.setattr(media, "get_fps", lambda path: 30.0)
    monkeypatch.setattr(
        __import__("precutter.silence", fromlist=["x"]), "detect_silence",
        lambda *a, **k: [])
    cached = {
        "language": "en",
        "words": [{"text": "go", "start": 1.0, "end": 1.5,
                   "prob": 0.95, "filler": False}],
        "fillers": [], "speech": [[0.0, 10.0]], "music": [],
        "silence": [], "filler_ratio": 0.0, "duration": 10.0}
    monkeypatch.setattr(transcribe_mod, "load_cache", lambda *a, **k: cached)
    monkeypatch.setattr(score_mod, "installed_models", lambda host=None: None)
    req = app_module.ProcessRequest(filename="v.mp4", ai_cut=True)
    _, keep, summary = app_module._analyze_file(target, req)
    assert keep == [[0.0, 10.0]]  # score 70, nothing below threshold
    assert summary["ai_cut_count"] == 0
    assert summary["ai_source"] == "heuristic"
    assert summary["_scores"] and summary["_scores"][0]["score"] == 70


def test_detect_highlights_never_fails_analysis(tmp_path):
    """Decode failure -> [] so the analyze job still completes."""
    fake = tmp_path / "v.mp4"
    fake.write_bytes(b"0" * 16)
    req = app_module.ProcessRequest(filename="v.mp4")
    out = app_module._detect_highlights(
        fake, req, 10.0, speech=[], music=[], on_stage=None)
    assert out == []
