"""Tests for transcribe helpers (no models required)."""
import numpy as np

from precutter import transcribe as t


def _w(text, s, e, prob=0.9):
    return t.Word(text=text, start=s, end=e, prob=prob,
                  filler=t.normalize_word(text) in t.filler_set("tr"))


def test_normalize_word_tr():
    assert t.normalize_word("Şey,") == "şey"
    assert t.normalize_word("Yani!") == "yani"


def test_filler_sets():
    assert "şey" in t.filler_set("tr")
    assert "um" in t.filler_set("en")
    assert "şey" in t.filler_set(None)  # auto = birlesik


def test_filler_ratio_and_intervals():
    words = [_w("merhaba", 0.0, 0.5), _w("şey", 0.6, 0.9), _w("dünya", 1.0, 1.5),
             _w("yani", 1.6, 1.9)]
    fillers = [w for w in words if w.filler]
    assert len(fillers) == 2
    ratio = len(fillers) / len(words)
    assert ratio == 0.5
    iv = t.filler_intervals(words, pad=0.0)
    assert iv == [(0.6, 0.9), (1.6, 1.9)]


def test_merge_and_subtract_intervals():
    assert t.merge_intervals([(0, 1), (0.9, 2), (5, 6)], max_gap=0.0) == [(0, 2), (5, 6)]
    assert t.subtract_intervals([(0, 10)], [(2, 4), (6, 8)]) == [(0, 2), (4, 6), (8, 10)]
    assert t.subtract_intervals([], [(1, 2)]) == []


def test_words_to_speech_and_silence():
    words = [_w("a", 1.0, 1.5), _w("b", 1.6, 2.0)]
    speech = t.words_to_speech(words, max_gap=0.4, pad=0.0, duration=5.0)
    assert speech == [(1.0, 2.0)]
    silence = t.silence_from_speech(speech, 5.0)
    assert silence == [(0.0, 1.0), (2.0, 5.0)]


def test_whisper_music_candidates():
    segs = [
        {"start": 0.0, "end": 3.0, "no_speech_prob": 0.9},
        {"start": 4.0, "end": 6.0, "no_speech_prob": 0.1},
        {"start": 7.0, "end": 7.5, "no_speech_prob": 0.95},  # cok kisa
    ]
    assert t.whisper_music_candidates(segs) == [(0.0, 3.0)]


def test_tonal_music_mask_silence_returns_empty():
    sr = t.SAMPLE_RATE
    quiet = np.zeros(sr * 2, dtype=np.float32)
    assert t.tonal_music_mask(quiet) == []


def test_tonal_music_mask_sustained_tone_detected():
    sr = t.SAMPLE_RATE
    duration_s = 4.0
    tt = np.arange(int(sr * duration_s)) / sr
    tone = (0.5 * np.sin(2 * np.pi * 440 * tt)).astype(np.float32)
    mask = t.tonal_music_mask(tone)
    assert len(mask) >= 1
    # Muzik tum sureye yakin kapsanmali.
    covered = sum(e - s for s, e in mask)
    assert covered >= duration_s * 0.5


def test_build_music_layer_removes_confirmed_speech():
    import numpy as np
    sr = t.SAMPLE_RATE
    tt = np.arange(sr * 4) / sr
    tone = (0.5 * np.sin(2 * np.pi * 440 * tt)).astype(np.float32)
    segs = [{"start": 0.0, "end": 4.0, "no_speech_prob": 0.9}]
    # 1.0-2.0 arasi kesin konusma -> muzikten cikarilmali.
    music = t.build_music_layer(tone, segs, confirmed_speech=[(1.0, 2.0)])
    for s, e in music:
        assert e <= 1.0 or s >= 2.0


def test_cache_key_stable():
    assert t.cache_key("abc", "base", None) == t.cache_key("abc", "base", "auto")
    assert t.cache_key("abc", "base", "tr") != t.cache_key("abc", "base", "en")
