"""Tests for transcribe helpers (no models required)."""
import time

import numpy as np
from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import transcribe as t

client = TestClient(app_module.app)


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


def test_chunk_windows_cover_all_samples():
    wins = list(t._chunk_windows(130 * 16000, 16000))
    assert len(wins) == 3
    starts = [w[0] for w in wins]
    assert starts == [0.0, 60.0, 120.0]
    # Last window reaches the end, middle windows carry the overlap.
    assert wins[0][1].stop - wins[0][1].start == 62 * 16000
    assert wins[2][1].stop == 130 * 16000


def test_chunk_windows_short_audio_is_single():
    wins = list(t._chunk_windows(10 * 16000, 16000))
    assert len(wins) == 1
    assert wins[0] == (0.0, slice(0, 10 * 16000, None))


class _FakeWord:
    def __init__(self, word, start, end, prob=0.9):
        self.word = word
        self.start = start
        self.end = end
        self.probability = prob


class _FakeSeg:
    def __init__(self, start, end, words, lang_prob=0.1):
        self.start = start
        self.end = end
        self.words = words
        self.no_speech_prob = lang_prob
        self.avg_logprob = -0.2


class _FakeModel:
    def __init__(self):
        self.calls = []
        self.n = 0

    def transcribe(self, audio, **kwargs):
        self.calls.append((len(audio), kwargs.get("language")))
        self.n += 1
        # First chunk: word near its start; later chunks: mid-chunk word
        # (outside the overlapped head, so it is kept with its offset).
        rel = 0.5 if self.n == 1 else 30.0
        info = type("Info", (), {"language": "en"})()
        seg = _FakeSeg(rel, rel + 1.0, [_FakeWord("hello", rel, rel + 0.5)])
        return [seg], info


def test_chunked_transcribe_merges_offsets_and_progress(monkeypatch, tmp_path):
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    # 130 s of fake audio -> 3 chunks; skip VAD/music layers.
    import numpy as _np

    monkeypatch.setattr(t, "read_wav_mono",
                        lambda path, sr=16000: _np.zeros(130 * 16000, dtype=_np.float32))
    monkeypatch.setattr(t, "silero_speech", lambda path: [])
    monkeypatch.setattr(t, "energy_speech_fallback", lambda path: [])
    monkeypatch.setattr(t, "build_music_layer", lambda *a, **k: [])
    monkeypatch.setattr(t, "extract_wav", lambda *a, **k: target)
    from precutter import media as _media

    monkeypatch.setattr(_media, "get_duration", lambda path: 130.0)

    calls = []
    model_holder = {}

    def fake_load(model_size="base"):
        m = _FakeModel()
        model_holder["m"] = m
        return m

    monkeypatch.setattr(t, "_load_whisper", fake_load)
    tr = t.transcribe_file(target, model_size="tiny", use_cache=False,
                           use_silero=False, detect_music=False,
                           progress=lambda d, n: calls.append((d, n)))
    assert calls == [(1, 3), (2, 3), (3, 3)]
    # Offsets applied per chunk: 0.5, 60+30, 120+30.
    assert [w.start for w in tr.words] == [0.5, 90.0, 150.0]
    assert tr.language == "en"
    assert len(model_holder["m"].calls) == 3


def test_chunked_transcribe_dedups_overlap(monkeypatch, tmp_path):
    """A word starting inside the overlapped head is kept once."""
    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)

    class OverlapModel:
        def transcribe(self, audio, **kwargs):
            info = type("Info", (), {"language": "en"})()
            # Same relative word in every chunk: absolute 1.0, 61.0, 121.0.
            # The latter two sit inside overlapped heads -> dropped.
            seg = _FakeSeg(1.0, 1.5, [_FakeWord("hi", 1.0, 1.4)])
            return [seg], info

    import numpy as _np

    monkeypatch.setattr(t, "_load_whisper", lambda model_size="base": OverlapModel())
    monkeypatch.setattr(t, "read_wav_mono",
                        lambda path, sr=16000: _np.zeros(130 * 16000, dtype=_np.float32))
    monkeypatch.setattr(t, "silero_speech", lambda path: [])
    monkeypatch.setattr(t, "energy_speech_fallback", lambda path: [])
    monkeypatch.setattr(t, "build_music_layer", lambda *a, **k: [])
    monkeypatch.setattr(t, "extract_wav", lambda *a, **k: target)
    from precutter import media as _media

    monkeypatch.setattr(_media, "get_duration", lambda path: 130.0)
    tr = t.transcribe_file(target, model_size="tiny", use_cache=False,
                           use_silero=False, detect_music=False)
    assert [w.start for w in tr.words] == [1.0]


def test_transcribe_endpoint_is_job_based(monkeypatch, tmp_path):
    from precutter import media as _media

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(_media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        _media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}])

    from precutter import transcribe as transcribe_mod

    fake_words = [t.Word(text="um", start=1.0, end=1.5, filler=True)]

    class FakeTranscript:
        words = fake_words
        fillers = fake_words

        def to_dict(self):
            return {"words": [{"text": "um", "start": 1.0, "end": 1.5,
                               "prob": 0.9, "filler": True}],
                    "fillers": [{"text": "um", "start": 1.0, "end": 1.5,
                                 "prob": 0.9, "filler": True}],
                    "filler_ratio": 1.0, "language": "en"}

    monkeypatch.setattr(transcribe_mod, "transcribe_file",
                        lambda *a, **k: FakeTranscript())
    resp = client.post("/transcribe", json={
        "filename": "v.mp4", "remove_fillers": True, "audio_track": 0})
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    deadline = time.time() + 10
    job = {}
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert job["result"]["filler_ratio"] == 1.0
    assert job["result"]["filler_intervals"] == [[0.95, 1.55]]


def _patch_transcribe_env(monkeypatch, tmp_path, fake_transcribe):
    """Ortak kurulum: dosya + süre + ses izi + transcribe_file sahtesi."""
    from precutter import media as _media

    target = tmp_path / "v.mp4"
    target.write_bytes(b"0" * 16)
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(_media, "get_duration", lambda path: 10.0)
    monkeypatch.setattr(
        _media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}])
    from precutter import transcribe as transcribe_mod

    monkeypatch.setattr(transcribe_mod, "transcribe_file", fake_transcribe)
    return target


def test_transcribe_identical_request_joins_running_job(monkeypatch, tmp_path):
    """İkinci özdeş istek yeni Whisper başlatmaz; aynı job_id'ye katılır."""
    import threading

    started = threading.Event()
    release = threading.Event()
    calls = []

    def fake_transcribe(*a, **k):
        calls.append(1)
        started.set()
        release.wait(timeout=10)
        fake_words = [t.Word(text="um", start=1.0, end=1.5, filler=True)]
        tr = type("Fake", (), {})()
        tr.words = fake_words
        tr.to_dict = lambda: {"words": [], "fillers": [], "filler_ratio": 0.0}
        return tr

    _patch_transcribe_env(monkeypatch, tmp_path, fake_transcribe)
    body = {"filename": "v.mp4", "remove_fillers": True, "audio_track": 0}
    first = client.post("/transcribe", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["deduped"] is False
    assert started.wait(timeout=5)

    second = client.post("/transcribe", json=body)
    assert second.status_code == 200, second.text
    assert second.json()["deduped"] is True
    assert second.json()["job_id"] == first.json()["job_id"]
    assert len(calls) == 1  # ikinci Whisper yok

    release.set()
    deadline = time.time() + 10
    job = {}
    while time.time() < deadline:
        job = client.get(f"/jobs/{first.json()['job_id']}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job


def test_transcribe_different_track_starts_separate_job(monkeypatch, tmp_path):
    """Farklı ses izi farklı iştir; dedup'a takılmaz."""
    import threading

    started = threading.Event()
    release = threading.Event()

    def fake_transcribe(*a, **k):
        started.set()
        release.wait(timeout=10)
        tr = type("Fake", (), {})()
        tr.words = []
        tr.to_dict = lambda: {"words": [], "fillers": [], "filler_ratio": 0.0}
        return tr

    _patch_transcribe_env(monkeypatch, tmp_path, fake_transcribe)
    monkeypatch.setattr(
        app_module.media, "audio_streams",
        lambda path, **kw: [{"track": 0, "channels": 2}, {"track": 1, "channels": 1}])
    a = client.post("/transcribe", json={"filename": "v.mp4", "audio_track": 0})
    assert started.wait(timeout=5)
    b = client.post("/transcribe", json={"filename": "v.mp4", "audio_track": 1})
    assert a.json()["job_id"] != b.json()["job_id"]
    release.set()


def test_transcribe_job_waits_for_heavy_slot(monkeypatch, tmp_path):
    """Ağır iş doluysa yeni transkript job'u 'queued'da bekler."""
    started = []

    def fake_transcribe(*a, **k):
        started.append(1)
        tr = type("Fake", (), {})()
        tr.words = []
        tr.to_dict = lambda: {"words": [], "fillers": [], "filler_ratio": 0.0}
        return tr

    _patch_transcribe_env(monkeypatch, tmp_path, fake_transcribe)
    assert app_module._HEAVY_SEM.acquire(timeout=5)  # slotu biz tut
    try:
        resp = client.post("/transcribe", json={"filename": "v.mp4", "audio_track": 0})
        job_id = resp.json()["job_id"]
        time.sleep(0.2)
        job = client.get(f"/jobs/{job_id}").json()
        assert job["stage"] == "queued", job
        assert not started  # işçi slotu bekliyor
    finally:
        app_module._HEAVY_SEM.release()
    deadline = time.time() + 10
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert started


def test_whisper_device_and_load_uses_it(monkeypatch):
    assert t.whisper_device() in ("cpu", "cuda")
    monkeypatch.setattr(t, "_whisper_cache", {})
    monkeypatch.setattr(t, "whisper_device", lambda: "cpu")
    captured = {}

    class FakeWhisperModel:
        def __init__(self, size, device=None, compute_type=None):
            captured.update(size=size, device=device, compute_type=compute_type)

    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisperModel)
    t._load_whisper("base")
    assert captured == {"size": "base", "device": "cpu", "compute_type": "int8"}


def test_doctor_reports_whisper_device():
    resp = client.get("/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert "whisper_device" in data
    assert data["whisper_device"] in ("cpu", "cuda", None)
