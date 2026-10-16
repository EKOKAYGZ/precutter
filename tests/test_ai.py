"""v0.4 AI scoring: prompt parsing, batching, fallback, chat, frames."""
import json

import pytest
from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config, media
from precutter import score as score_mod

client = TestClient(app_module.app)


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_chat_factory(reply, calls):
    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return FakeResp({"message": {"content": reply}})
    return fake_post


@pytest.fixture()
def no_score_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(
        score_mod, "cache_path", lambda key: tmp_path / key)
    return tmp_path


def test_parse_scores_ok_and_missing():
    out = score_mod._parse_scores(
        '{"scores":[{"id":0,"score":85,"why":"funny"},{"id":1,"score":20,"why":"restart"}]}',
        [0, 1])
    assert out[0] == (85, "funny")
    assert out[1][0] == 20
    with pytest.raises(score_mod.OllamaError):
        score_mod._parse_scores('{"scores":[{"id":0,"score":50}]}', [0, 1])
    with pytest.raises(score_mod.OllamaError):
        score_mod._parse_scores("not json at all", [0])


def test_segment_texts_truncates_and_skips_empty():
    from precutter import transcribe as transcribe_mod

    words = [transcribe_mod.Word(f"w{i}", i * 0.5, i * 0.5 + 0.3) for i in range(300)]
    segs = score_mod.segment_texts([[0.0, 200.0], [500.0, 501.0]], words)
    assert len(segs) == 1  # second segment has no words
    assert segs[0]["text"].endswith("…")
    assert len(segs[0]["text"].split()) <= score_mod.MAX_WORDS_PER_SEGMENT + 1


def test_heuristic_score_table():
    from precutter import transcribe as transcribe_mod

    good = [transcribe_mod.Word("oyna", 0.0, 0.5, prob=0.95)]
    seg = {"id": 0, "start": 0.0, "end": 2.0, "text": "oyna"}
    s, reasons = score_mod.heuristic_score(good and seg, good, [], [])
    assert s == 70 and reasons == ["steady"]
    bad = [transcribe_mod.Word("ıı", 0.0, 0.4, prob=0.9, filler=True),
           transcribe_mod.Word("şey", 0.4, 0.8, prob=0.3, filler=True)]
    seg2 = {"id": 1, "start": 0.0, "end": 2.0, "text": "ıı şey"}
    s2, _ = score_mod.heuristic_score(seg2, bad, [], [])
    assert s2 < 50


def test_score_segments_llm_then_cache(monkeypatch, no_score_cache):
    import httpx
    from precutter import transcribe as transcribe_mod

    calls = []
    reply = json.dumps({"scores": [
        {"id": 0, "score": 90, "why": "highlight"},
        {"id": 1, "score": 15, "why": "restart"}]})
    monkeypatch.setattr(httpx, "post", _fake_chat_factory(reply, calls))
    monkeypatch.setattr(score_mod, "installed_models",
                        lambda host=None: ["qwen3:1.7b"])
    words = [transcribe_mod.Word("gol", 1.0, 1.5, prob=0.95),
             transcribe_mod.Word("ıı", 20.0, 20.4, prob=0.9, filler=True)]
    keep = [[0.0, 5.0], [18.0, 25.0]]
    first = score_mod.score_segments(words, keep, [], [], "tr", "football")
    assert first["source"] == "llm"
    assert [s["score"] for s in first["scores"]] == [83, 24]  # 0.65*llm + 0.35*heur
    assert score_mod.cuts_below_threshold(first["scores"], 30) == [[18.0, 25.0]]
    n_calls = len(calls)
    assert n_calls >= 1
    second = score_mod.score_segments(words, keep, [], [], "tr", "football")
    assert second["source"] == "llm"
    assert len(calls) == n_calls  # cache hit: no new Ollama call


def test_score_segments_falls_back_to_heuristic(monkeypatch, no_score_cache):
    import httpx
    from precutter import transcribe as transcribe_mod

    def boom(url, json=None, timeout=None):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    monkeypatch.setattr(score_mod, "installed_models", lambda host=None: None)
    words = [transcribe_mod.Word("gol", 1.0, 1.5, prob=0.95)]
    out = score_mod.score_segments(words, [[0.0, 5.0]], [], [], "tr", "x")
    assert out["source"] == "heuristic"
    assert out["scores"][0]["score"] == 70


def test_ensure_model_missing_hint():
    import pytest as _pt

    orig = score_mod.installed_models
    score_mod.installed_models = lambda host=None: ["other:1b"]
    try:
        with _pt.raises(score_mod.OllamaError, match="ollama pull"):
            score_mod._ensure_model("http://x", "qwen3:1.7b")
    finally:
        score_mod.installed_models = orig


def test_chat_ollama_down_is_502(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 60.0)
    monkeypatch.setattr(score_mod, "installed_models", lambda host=None: None)
    resp = client.post("/chat", json={"filename": "v.mp4", "message": "ne var?"})
    assert resp.status_code == 502, resp.text
    assert "llama" in resp.json()["detail"].lower() or "pull" in resp.json()["detail"].lower()


def test_chat_endpoint(monkeypatch, tmp_path):
    from precutter import transcribe as transcribe_mod

    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    (tmp_path / "v.mp4").write_bytes(b"0" * 16)
    monkeypatch.setattr(media, "get_duration", lambda path: 60.0)
    cached = {"language": "tr",
              "words": [{"text": "gol", "start": 1.0, "end": 1.5,
                         "prob": 0.95, "filler": False}],
              "fillers": [], "speech": [[0.0, 5.0]], "music": [],
              "silence": [], "filler_ratio": 0.0, "duration": 60.0}
    monkeypatch.setattr(transcribe_mod, "load_cache", lambda *a, **k: cached)
    monkeypatch.setattr(score_mod, "answer_chat",
                        lambda *a, **k: "1. saniyede gol var.")
    resp = client.post("/chat", json={
        "filename": "v.mp4", "message": "gol ne zaman?", "history": []})
    assert resp.status_code == 200, resp.text
    assert "gol" in resp.json()["reply"]
    assert client.post("/chat", json={
        "filename": "v.mp4", "message": "  "}).status_code == 400


def test_frames_fallback_without_vision(monkeypatch, tmp_path):
    from precutter import frames as frames_mod

    monkeypatch.setattr(score_mod, "installed_models", lambda host=None: None)
    out = frames_mod.classify_content(tmp_path / "v.mp4", 60.0, "fp123")
    assert out["label"] == "general video"
    assert out["model"] is None


def test_pick_vision_model_order():
    from precutter import frames as frames_mod

    orig = score_mod.installed_models
    score_mod.installed_models = lambda host=None: ["gemma3:4b", "qwen3:1.7b"]
    try:
        assert frames_mod.pick_vision_model("http://x") == "gemma3:4b"
    finally:
        score_mod.installed_models = orig
