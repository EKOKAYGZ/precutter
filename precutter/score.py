"""v0.4 LLM importance scoring via Ollama (default qwen3-vl:4b).

Design for small models (1.7B class, CPU-friendly):
- Short, strict prompts: batched windows, JSON-only, temperature 0,
  no thinking, small num_predict. Fewer, bigger calls beat many small ones.
- Conservative by default: unsure -> keep (score 70+), so a weak model can
  only cut what is clearly bad.
- Any LLM failure (down/timeout/bad JSON) -> heuristic-only fallback that
  still produces scores and cuts. The analysis never dies because of AI.
- Scores are cached next to transcripts, keyed by transcript fingerprint.
"""
import hashlib
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import config
from .media import MediaError

AI_MODEL_DEFAULT = "qwen3-vl:4b"

SEGMENTS_PER_CALL = 6
MAX_WORDS_PER_SEGMENT = 200
CONNECT_TIMEOUT = 5.0
CALL_TIMEOUT = 180.0

SYSTEM_V1 = (
    "You judge transcript parts for a video cut editor. "
    "Reply with JSON only, no other text."
)

USER_TEMPLATE = (
    "Content: {label}. Language: {lang}.\n"
    "Rate each part 0-100 for KEEP-worthiness: highlights, funny or "
    "important speech = high. Filler, stuttered restarts, dead mumbling, "
    "repeated failed takes = low. Be conservative: when unsure, score 70+.\n"
    "Parts:\n{parts}\n"
    'Reply exactly: {{"scores":[{{"id":N,"score":N,"why":"short reason"}}]}} '
    "with every id exactly once.\n"
    "Example: parts [7] \"uh i i mean let's go\" -> "
    "'{{\"scores\":[{{\"id\":7,\"score\":20,\"why\":\"stuttered restart\"}}]}}'"
)


class OllamaError(MediaError):
    """Ollama unreachable / model missing / bad reply."""


def _host() -> str:
    return (config.OLLAMA_HOST or "http://127.0.0.1:11434").rstrip("/")


def _model() -> str:
    return config.AI_MODEL or AI_MODEL_DEFAULT


def installed_models(host: Optional[str] = None) -> Optional[List[str]]:
    """Model names in Ollama. None when Ollama is down (no exception)."""
    import httpx

    try:
        r = httpx.get(f"{host or _host()}/api/tags",
                      timeout=CONNECT_TIMEOUT)
        r.raise_for_status()
        return [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return None


def _ensure_model(host: str, model: str) -> None:
    names = installed_models(host)
    if names is None:
        raise OllamaError(
            f"Ollama is not reachable at {host}. Start it with `ollama serve`.")
    if not any(n == model or n.startswith(model + ":") for n in names):
        raise OllamaError(
            f"Model '{model}' is not in Ollama. Run `ollama pull {model}` once, "
            f"then retry. Installed: {', '.join(names[:8]) or 'none'}.")


def _chat(host: str, model: str, system: str, user: str,
          num_predict: int, timeout: float = CALL_TIMEOUT) -> str:
    import httpx

    try:
        r = httpx.post(
            f"{host}/api/chat",
            json={"model": model, "think": False, "stream": False,
                  "format": "json",
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                  "options": {"temperature": 0, "num_predict": num_predict}},
            timeout=timeout)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")
    except OllamaError:
        raise
    except Exception as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc


def _parse_scores(reply: str, ids: List[int]) -> Dict[int, Tuple[int, str]]:
    """{id: (score, why)}. Raises OllamaError on any shape problem."""
    try:
        data = json.loads(reply)
    except (ValueError, TypeError) as exc:
        raise OllamaError(f"Bad JSON from model: {reply[:120]!r}") from exc
    items = data.get("scores") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise OllamaError("Model reply has no 'scores' list.")
    out: Dict[int, Tuple[int, str]] = {}
    for it in items:
        try:
            i = int(it["id"])
            s = max(0, min(100, int(it["score"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise OllamaError(f"Bad score entry: {it!r}") from exc
        if i in ids:
            out[i] = (s, str(it.get("why", ""))[:60])
    missing = [i for i in ids if i not in out]
    if missing:
        raise OllamaError(f"Model skipped ids: {missing}.")
    return out


def segment_texts(keep: List, words: List) -> List[Dict[str, Any]]:
    """Keep-segment -> {id, start, end, text} (truncated for small models)."""
    out = []
    for i, seg in enumerate(keep):
        s = float(seg[0]) if isinstance(seg, (list, tuple)) else float(seg.get("start", seg.get("s")))
        e = float(seg[1]) if isinstance(seg, (list, tuple)) else float(seg.get("end", seg.get("e")))
        toks = [w.text for w in words
                if getattr(w, "start", 0) >= s - 0.05 and getattr(w, "end", 0) <= e + 0.05]
        if len(toks) > MAX_WORDS_PER_SEGMENT:
            toks = toks[:MAX_WORDS_PER_SEGMENT] + ["…"]
        out.append({"id": i, "start": round(s, 3), "end": round(e, 3),
                    "text": " ".join(toks)})
    return [w for w in out if w["text"].strip(" …")]


def heuristic_score(seg: Dict[str, Any], words: List,
                    music: List, highlights: List) -> Tuple[int, List[str]]:
    """No-LLM score 0-100: filler/confidence density, music, highlights."""
    s, e = seg["start"], seg["end"]
    inside = [w for w in words
              if getattr(w, "start", 0) >= s - 0.05 and getattr(w, "end", 0) <= e + 0.05]
    score = 70
    reasons: List[str] = []
    if inside:
        fill = sum(1 for w in words_filler(inside)) / len(inside)
        lowc = sum(1 for w in inside if getattr(w, "prob", 1.0) < 0.5) / len(inside)
        if fill > 0.05:
            score -= round(30 * min(1.0, fill * 3))
            reasons.append(f"filler{fill:.0%}")
        if lowc > 0.1:
            score -= round(20 * min(1.0, lowc * 2))
            reasons.append("mumbled")
    if _overlaps(s, e, music):
        if inside:
            # Ses "müzik" diyor ama kelime var: arka plan müzikli konuşma.
            score += 5
            reasons.append("speech+music")
        else:
            score -= 15
            reasons.append("over-music")
    if _overlaps(s, e, highlights):
        score += 15
        reasons.append("highlight")
    if not reasons:
        reasons.append("steady")
    return max(0, min(100, score)), reasons


def words_filler(inside: List) -> List:
    return [w for w in inside if getattr(w, "filler", False)]


def _overlaps(s: float, e: float, intervals: List) -> bool:
    for iv in intervals or []:
        if isinstance(iv, (list, tuple)):
            a, b = float(iv[0]), float(iv[1])
        else:
            a = float(iv.get("start", iv.get("s", 0)))
            b = float(iv.get("end", iv.get("e", 0)))
        if a < e and b > s:
            return True
    return False


def score_batch(host: str, model: str, batch: List[Dict[str, Any]],
                label: str, lang: str) -> Dict[int, Tuple[int, str]]:
    """One LLM call for up to SEGMENTS_PER_CALL segments."""
    parts = "\n".join(
        f'[{w["id"]}] ({w["start"]}-{w["end"]}s) "{w["text"]}"' for w in batch)
    user = USER_TEMPLATE.format(label=label or "general video",
                                lang=lang or "auto", parts=parts)
    reply = _chat(host, model, SYSTEM_V1, user,
                  num_predict=128 + 96 * len(batch))
    return _parse_scores(reply, [w["id"] for w in batch])


def _cache_key(fingerprint: str, model: str, lang: str,
                 vision_fp: str = "") -> str:
    raw = f"{fingerprint}|{model}|{lang}|{vision_fp}|v2".encode()
    return "score_" + hashlib.sha256(raw).hexdigest()[:32] + ".json"


def vision_for_segment(vision: Optional[List[Dict[str, Any]]],
                       s: float, e: float) -> Optional[Tuple[int, str]]:
    """Segmentle örtüşen slice'ların süre-ağırlıklı vizyon skoru."""
    if not vision:
        return None
    total, acc = 0.0, 0.0
    label_votes: Dict[str, float] = {}
    for sl in vision:
        a, b = float(sl["start"]), float(sl["end"])
        ov = max(0.0, min(e, b) - max(s, a))
        if ov > 0:
            total += ov
            acc += ov * int(sl.get("score", 70))
            label_votes[str(sl.get("label", ""))] = \
                label_votes.get(str(sl.get("label", "")), 0.0) + ov
    if total <= 0:
        return None
    label = max(label_votes, key=lambda k: label_votes[k])
    return round(acc / total), label


def cache_path(key: str):
    from . import transcribe as transcribe_mod

    return transcribe_mod.cache_dir() / key


def score_segments(words: List, keep: List, music: List, highlights: List,
                   language: str, label: str,
                   progress: Optional[Callable[[int, int], None]] = None,
                   host: Optional[str] = None,
                   model: Optional[str] = None,
                   vision: Optional[List[Dict[str, Any]]] = None
                   ) -> Dict[str, Any]:
    """Score keep-segments. Returns {scores, source, model}.

    source is "llm" or "heuristic" (LLM down/bad reply -> fallback).
    Vision slices (when present) weigh 0.2: 0.5*llm + 0.2*vision + 0.3*heur.
    Results cached by transcript fingerprint (+ vision hash).
    """
    from . import transcribe as transcribe_mod

    host = host or _host()
    model = model or _model()
    segs = segment_texts(keep, words)
    heur = {w["id"]: heuristic_score(w, words, music, highlights) for w in segs}
    if not segs:
        return {"scores": [], "source": "heuristic", "model": model}
    # Transcript fingerprint for cache (words only, stable across runs).
    fp_src = "|".join(
        f"{getattr(w, 'text', '')}@{getattr(w, 'start', 0):.2f}" for w in words)
    fp = hashlib.sha256(fp_src.encode("utf-8", "replace")).hexdigest()[:32]
    vision_fp = ""
    if vision:
        vision_fp = hashlib.sha256(json.dumps(
            [(v.get("start"), v.get("end"), v.get("label"), v.get("score"))
             for v in vision]).encode()).hexdigest()[:16]
    key = _cache_key(fp, model, language or "auto", vision_fp)
    try:
        cached = json.loads(cache_path(key).read_text(encoding="utf-8"))
        if isinstance(cached, dict) and cached.get("fp") == fp:
            if progress:
                progress(1, 1)
            return {"scores": cached["scores"], "source": cached.get("source", "llm"),
                    "model": model}
    except (OSError, ValueError, KeyError):
        pass
    llm: Dict[int, Tuple[int, str]] = {}
    source = "heuristic"
    try:
        _ensure_model(host, model)
        batches = [segs[i:i + SEGMENTS_PER_CALL]
                   for i in range(0, len(segs), SEGMENTS_PER_CALL)]
        for bi, batch in enumerate(batches):
            for attempt in range(2):
                try:
                    llm.update(score_batch(host, model, batch, label, language))
                    break
                except OllamaError:
                    if attempt == 1:
                        raise
            if progress:
                progress(bi + 1, len(batches))
        source = "llm"
    except OllamaError:
        llm = {}
        if progress:
            progress(1, 1)
    scores = []
    for w in segs:
        h, hreasons = heur[w["id"]]
        vis = vision_for_segment(vision, w["start"], w["end"])
        if w["id"] in llm:
            ls, why = llm[w["id"]]
            if vis is not None:
                vs, vlabel = vis
                final = round(0.5 * ls + 0.2 * vs + 0.3 * h)
                reasons = ([why] if why else []) + [f"seen:{vlabel}"] + hreasons[:1]
            else:
                final = round(0.65 * ls + 0.35 * h)
                reasons = ([why] if why else []) + hreasons[:2]
        elif vis is not None:
            vs, vlabel = vis
            final = round(0.7 * h + 0.3 * vs)
            reasons = [f"seen:{vlabel}"] + hreasons[:2]
        else:
            final, reasons = h, hreasons
        scores.append({"start": w["start"], "end": w["end"],
                       "score": max(0, min(100, final)),
                       "reasons": reasons[:3], "id": w["id"]})
    try:
        cache_path(key).write_text(
            json.dumps({"fp": fp, "scores": scores, "source": source}),
            encoding="utf-8")
    except OSError:
        pass
    return {"scores": scores, "source": source, "model": model}


def cuts_below_threshold(scores: List[Dict[str, Any]],
                         threshold: int) -> List[List[float]]:
    """Score-threshold altı segmentler -> kesim aralıkları."""
    return [[s["start"], s["end"]] for s in scores if s["score"] < threshold]


CHAT_SYSTEM = (
    "You are the video assistant of PreCutter, a local cut editor. "
    "Answer briefly (max 120 words) using ONLY the context below. "
    "Times are seconds in the ORIGINAL video. "
    "If the answer is not in the context, say so honestly."
)


def answer_chat(host: str, model: str, context: str,
                history: List[Dict[str, str]], message: str,
                timeout: float = 300.0) -> str:
    """Free-form video Q&A (chat tab). Raises OllamaError on failure."""
    _ensure_model(host, model)
    import httpx

    msgs = [{"role": "system",
             "content": CHAT_SYSTEM + "\n\nCONTEXT:\n" + context[:9000]}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": str(h["content"])[:1500]})
    msgs.append({"role": "user", "content": message[:2000]})
    try:
        r = httpx.post(
            f"{host}/api/chat",
            json={"model": model, "think": False, "stream": False,
                  "messages": msgs,
                  "options": {"temperature": 0.2, "num_predict": 512}},
            timeout=timeout)
        r.raise_for_status()
        return (r.json().get("message", {}).get("content", "") or "").strip()
    except OllamaError:
        raise
    except Exception as exc:
        raise OllamaError(f"Ollama chat failed: {exc}") from exc
