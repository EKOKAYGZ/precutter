"""Vision context: slicing, slice calls, music rule, fallbacks, wiring."""
import json

import pytest

from precutter import app as app_module
from precutter import config, media
from precutter import frames as frames_mod
from precutter import score as score_mod


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def no_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(score_mod, "cache_path", lambda key: tmp_path / key)
    monkeypatch.setattr(frames_mod, "_cache_path",
                        lambda fp, model: tmp_path / f"slices_{model}.json")
    return tmp_path


def _words():
    from precutter import transcribe as transcribe_mod

    return [transcribe_mod.Word("oyna", 10.0, 10.5, prob=0.95),
            transcribe_mod.Word("gol", 200.0, 200.5, prob=0.9)]


class FakeTranscript:
    speech = [[0.0, 300.0]]
    silence = []
    music = []
    language = "tr"


def _tr():
    t = FakeTranscript()
    t.words = _words()
    return t


def test_slice_bounds_clamped():
    assert len(frames_mod.slice_bounds(60.0)) == 4
    assert len(frames_mod.slice_bounds(600.0)) == 5
    assert len(frames_mod.slice_bounds(3000.0)) == 24
    assert len(frames_mod.slice_bounds(7200.0)) == 24
    b = frames_mod.slice_bounds(600.0)
    assert b[0][0] == 0.0 and b[-1][1] == 600.0


def test_slice_transcript_and_ratios():
    words = _words()
    assert frames_mod.slice_transcript(words, 0.0, 120.0) == "oyna"
    assert frames_mod.slice_transcript(words, 120.0, 240.0) == "gol"
    r = frames_mod.slice_ratios(0.0, 120.0, [[0.0, 60.0]], [[60.0, 120.0]], [])
    assert r == {"speech": 50, "silence": 50, "music": 0}


def test_parse_slice_validates():
    ok = frames_mod._parse_slice(
        '{"label":"gameplay","score":85,"reason":"rush"}')
    assert ok == {"label": "gameplay", "score": 85, "reason": "rush"}
    with pytest.raises(score_mod.OllamaError):
        frames_mod._parse_slice('{"label":"movie","score":50}')
    with pytest.raises(score_mod.OllamaError):
        frames_mod._parse_slice("nope")


def test_analyze_slices_fallback_without_vision(monkeypatch, no_caches):
    monkeypatch.setattr(score_mod, "_ensure_model",
                        lambda *a, **k: (_ for _ in ()).throw(
                            score_mod.OllamaError("down")))
    out = frames_mod.analyze_slices(
        no_caches / "v.mp4", 600.0, _tr(), model="qwen3-vl:4b")
    # İkinci bir model istenmez: aynı model adıyla transcript-only devam.
    assert out == {"slices": [], "source": "transcript",
                   "model": "qwen3-vl:4b"}


def test_analyze_slices_vision_path_and_cache(monkeypatch, no_caches):
    import httpx

    calls = []
    replies = [
        '{"label":"talking-head","score":80,"reason":"intro"}',
        '{"label":"gameplay","score":90,"reason":"rush"}',
        '{"label":"menu-loading","score":20,"reason":"lobby"}',
        '{"label":"gameplay","score":75,"reason":"play"}',
        '{"label":"cutscene","score":60,"reason":"story"}',
    ]

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        assert "images" in json["messages"][1]
        assert json["model"] == "qwen3-vl:4b"
        assert json["think"] is False
        return FakeResp({"message": {"content": replies[len(calls) - 1]}})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(score_mod, "_ensure_model", lambda *a, **k: None)
    monkeypatch.setattr(frames_mod, "extract_frame",
                        lambda *a, **k: b"fakejpg")
    out = frames_mod.analyze_slices(
        no_caches / "v.mp4", 600.0, _tr(), model="qwen3-vl:4b")
    assert out["source"] == "vision"
    assert [s["label"] for s in out["slices"]] == [
        "talking-head", "gameplay", "menu-loading", "gameplay", "cutscene"]
    assert len(calls) == 5
    # Cache hit: no more calls.
    out2 = frames_mod.analyze_slices(
        no_caches / "v.mp4", 600.0, _tr(), model="qwen3-vl:4b")
    assert out2["slices"] == out["slices"]
    assert len(calls) == 5


def test_music_rule_speech_over_music():
    from precutter import transcribe as transcribe_mod

    spoken = [transcribe_mod.Word("gol", 1.0, 1.5, prob=0.95)]
    seg = {"id": 0, "start": 0.0, "end": 5.0, "text": "gol"}
    s, reasons = score_mod.heuristic_score(seg, spoken, [[0.0, 5.0]], [])
    assert "speech+music" in reasons
    assert "over-music" not in reasons
    assert s == 75
    seg_empty = {"id": 1, "start": 10.0, "end": 15.0, "text": ""}
    s2, reasons2 = score_mod.heuristic_score(seg_empty, [], [[10.0, 15.0]], [])
    assert "over-music" in reasons2
    assert s2 == 55


def test_vision_combine_weights(monkeypatch, no_caches):
    import httpx
    from precutter import transcribe as transcribe_mod

    reply = json.dumps({"scores": [{"id": 0, "score": 80, "why": "good"}]})
    monkeypatch.setattr(
        httpx, "post",
        lambda url, json=None, timeout=None: FakeResp(
            {"message": {"content": reply}}))
    monkeypatch.setattr(score_mod, "_ensure_model", lambda *a, **k: None)
    words = [transcribe_mod.Word("oyna", 1.0, 1.5, prob=0.95)]
    vision = [{"start": 0.0, "end": 10.0, "label": "gameplay",
               "score": 100, "reason": "rush"}]
    out = score_mod.score_segments(words, [[0.0, 10.0]], [], [], "tr", "x",
                                   model="m", vision=vision)
    # 0.5*80 + 0.2*100 + 0.3*70 = 81
    assert out["scores"][0]["score"] == 81
    assert "seen:gameplay" in out["scores"][0]["reasons"]


def test_analyze_file_uses_vision(monkeypatch, tmp_path, no_caches):
    from precutter import transcribe as transcribe_mod

    monkeypatch.setattr(config, "AI_MODEL", "qwen3-vl:4b")
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
        "language": "tr",
        "words": [{"text": "oyna", "start": 1.0, "end": 1.5,
                   "prob": 0.95, "filler": False}],
        "fillers": [], "speech": [[0.0, 10.0]], "music": [],
        "silence": [], "filler_ratio": 0.0, "duration": 10.0}
    monkeypatch.setattr(transcribe_mod, "load_cache", lambda *a, **k: cached)
    monkeypatch.setattr(
        frames_mod, "analyze_slices",
        lambda *a, **k: {"slices": [{"start": 0.0, "end": 10.0,
                                     "label": "gameplay", "score": 95,
                                     "reason": "rush"}],
                         "source": "vision", "model": "qwen3-vl:4b"})
    import httpx
    reply = json.dumps({"scores": [{"id": 0, "score": 90, "why": "good"}]})
    monkeypatch.setattr(
        httpx, "post",
        lambda url, json=None, timeout=None: FakeResp(
            {"message": {"content": reply}}))
    monkeypatch.setattr(score_mod, "_ensure_model", lambda *a, **k: None)
    req = app_module.ProcessRequest(filename="v.mp4", ai_cut=True)
    _, keep, summary = app_module._analyze_file(target, req)
    assert summary["ai_source"] == "llm"
    assert summary["ai_model"] == "qwen3-vl:4b"
    assert summary["content_label"] == "gameplay"
    assert keep == [[0.0, 10.0]]


def test_chat_context_includes_visual(monkeypatch, tmp_path):
    from precutter import transcribe as transcribe_mod

    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 600.0)
    cached = {"language": "tr",
              "words": [{"text": "gol", "start": 1.0, "end": 1.5,
                         "prob": 0.95, "filler": False}],
              "fillers": [], "speech": [[0.0, 600.0]], "music": [],
              "silence": [], "filler_ratio": 0.0, "duration": 600.0}
    monkeypatch.setattr(transcribe_mod, "load_cache", lambda *a, **k: cached)
    monkeypatch.setattr(
        frames_mod, "cached_slices",
        lambda fp, model: {"slices": [
            {"start": 0.0, "end": 120.0, "label": "gameplay",
             "score": 90, "reason": "rush"}]})
    req = app_module.ChatRequest(filename="v.mp4", message="ne oluyor?")
    ctx = app_module._chat_context(tmp_path / "v.mp4", req, "ne oluyor?")
    assert "[visual 0-120s] gameplay (90): rush" in ctx
