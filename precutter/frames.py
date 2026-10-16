"""Vision context: evenly-sampled frames + slice transcript, one model.

One Ollama model does vision AND scoring (default qwen3-vl:4b, think off).
Sampling is dumb on purpose: 1 frame every 2 minutes (min 4, max 24),
taken from the middle of each slice. Each slice goes out as ONE call
carrying frame + slice transcript + audio ratios, and comes back as
{label, score, reason}.

Fallback chain (nothing ever breaks analysis):
  vision model unavailable -> same model scores transcript-only
  Ollama down / model missing -> heuristic scoring
Cache key: file hash + model name.
"""
import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import config
from .media import MediaError

EVERY_S = 120
MIN_SLICES = 4
MAX_SLICES = 24
FRAME_WIDTH = 320

LABELS = ("gameplay", "talking-head", "static-screen", "menu-loading",
          "cutscene")

SLICE_SYSTEM = (
    "You watch one video slice: a frame plus its transcript. "
    "Reply with JSON only, no other text."
)

SLICE_USER = (
    "Video: {label_hint}. Slice {start}-{end}s.\n"
    "Transcript: \"{text}\"\n"
    "Audio: speech {speech_pct}%, silence {silence_pct}%, music {music_pct}%.\n"
    "Labels: gameplay | talking-head | static-screen | menu-loading | cutscene.\n"
    "If audio says music but there are spoken words, it is speech with "
    "background music, NOT a music scene.\n"
    "Keep-worthy (highlights, funny/important speech) scores high; filler, "
    "menus, loading screens score low. Unsure -> 70.\n"
    'Reply exactly: {{"label":"...","score":N,"reason":"short"}}'
)


def transcript_fingerprint(words: List) -> str:
    src = "|".join(
        f"{getattr(w, 'text', '')}@{getattr(w, 'start', 0):.2f}"
        for w in words)
    return hashlib.sha256(src.encode("utf-8", "replace")).hexdigest()[:32]


def slice_bounds(duration: float, every_s: int = EVERY_S,
                 min_n: int = MIN_SLICES,
                 max_n: int = MAX_SLICES) -> List[List[float]]:
    """Even slices covering [0, duration]. Count clamped min..max."""
    n = max(min_n, min(max_n, max(1, round(duration / every_s))))
    step = duration / n
    return [[round(i * step, 3), round(min(duration, (i + 1) * step), 3)]
            for i in range(n)]


def extract_frame(path: Path, at: float, width: int = FRAME_WIDTH) -> bytes:
    """One JPEG thumbnail at `at` seconds. Raises MediaError."""
    with tempfile.TemporaryDirectory(prefix="precutter-frame") as tmp:
        out = str(Path(tmp) / "f.jpg")
        cmd = [config.FFMPEG_BIN, "-hide_banner", "-nostats", "-v", "error",
               "-ss", f"{max(0.0, at):.3f}", "-i", str(path),
               "-frames:v", "1", "-vf", f"scale={width}:-1",
               "-q:v", "5", "-y", out]
        try:
            proc = subprocess.run(cmd, capture_output=True)
        except (FileNotFoundError, OSError) as exc:
            raise MediaError(f"ffmpeg not found: {exc}") from exc
        if proc.returncode != 0:
            raise MediaError("Could not extract frame.")
        try:
            return Path(out).read_bytes()
        except OSError as exc:
            raise MediaError(f"Could not read frame: {exc}") from exc


def slice_transcript(words: List, start: float, end: float,
                     max_words: int = 120) -> str:
    toks = [getattr(w, "text", "") for w in words
            if getattr(w, "start", 0) >= start - 0.05
            and getattr(w, "end", 0) <= end + 0.05]
    if len(toks) > max_words:
        toks = toks[:max_words] + ["…"]
    return " ".join(toks)


def slice_ratios(start: float, end: float, speech: List, silence: List,
                 music: List) -> Dict[str, int]:
    """Share of the slice covered by each audio layer (0-100)."""
    length = max(1e-6, end - start)

    def cover(intervals: List) -> float:
        total = 0.0
        for iv in intervals or []:
            if isinstance(iv, (list, tuple)):
                a, b = float(iv[0]), float(iv[1])
            else:
                a = float(iv.get("start", iv.get("s", 0)))
                b = float(iv.get("end", iv.get("e", 0)))
            total += max(0.0, min(end, b) - max(start, a))
        return round(100 * min(1.0, total / length))

    return {"speech": cover(speech), "silence": cover(silence),
            "music": cover(music)}


def _cache_path(fp: str, model: str) -> Path:
    from . import transcribe as transcribe_mod

    raw = f"{fp}|{model}|slices-v1".encode()
    return transcribe_mod.cache_dir() / (
        "slices_" + hashlib.sha256(raw).hexdigest()[:32] + ".json")


def cached_slices(fp: str, model: str) -> Optional[Dict]:
    try:
        data = json.loads(_cache_path(fp, model).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data.get("fp") == fp:
        return data
    return None


def _parse_slice(reply: str) -> Dict[str, Any]:
    from . import score as score_mod

    try:
        data = json.loads(reply)
    except (ValueError, TypeError) as exc:
        raise score_mod.OllamaError(f"Bad JSON from model: {reply[:120]!r}") from exc
    if not isinstance(data, dict):
        raise score_mod.OllamaError("Slice reply is not an object.")
    label = str(data.get("label", ""))
    if label not in LABELS:
        raise score_mod.OllamaError(f"Bad slice label: {label!r}.")
    try:
        score = max(0, min(100, int(data.get("score", 70))))
    except (TypeError, ValueError) as exc:
        raise score_mod.OllamaError("Bad slice score.") from exc
    return {"label": label, "score": score,
            "reason": str(data.get("reason", ""))[:80]}


def analyze_slices(path: Path, duration: float, transcript,
                   label_hint: str = "general video",
                   model: Optional[str] = None, host: Optional[str] = None,
                   progress: Optional[Callable[[int, int], None]] = None
                   ) -> Dict[str, Any]:
    """Slice vision pass. Returns {slices, source, model}.

    source "vision" on success, "transcript" when the vision model is
    unavailable (caller then scores text-only with the SAME model — no
    second model to install; qwen3-vl reads transcripts fine).
    Never raises for Ollama problems; frame-decode errors yield [].
    """
    from . import score as score_mod

    host = (host or config.OLLAMA_HOST
            or "http://127.0.0.1:11434").rstrip("/")
    model = model or config.AI_MODEL or "qwen3-vl:4b"
    words = getattr(transcript, "words", []) or []
    fp = transcript_fingerprint(words)
    hit = cached_slices(fp, model)
    if hit is not None:
        if progress:
            progress(1, 1)
        return {"slices": hit["slices"], "source": "vision", "model": model}
    try:
        score_mod._ensure_model(host, model)
    except score_mod.OllamaError:
        if progress:
            progress(1, 1)
        return {"slices": [], "source": "transcript", "model": model}
    bounds = slice_bounds(duration)
    speech = getattr(transcript, "speech", []) or []
    silence = getattr(transcript, "silence", []) or []
    music = getattr(transcript, "music", []) or []
    out: List[Dict[str, Any]] = []
    try:
        import httpx
    except ImportError:
        return {"slices": [], "source": "transcript", "model": model}
    for i, (start, end) in enumerate(bounds):
        try:
            frame = extract_frame(path, (start + end) / 2)
            user = SLICE_USER.format(
                label_hint=label_hint or "general video",
                start=round(start), end=round(end),
                text=slice_transcript(words, start, end)[:1500],
                **{f"{k}_pct": v for k, v in
                   slice_ratios(start, end, speech, silence, music).items()})
            r = httpx.post(
                f"{host}/api/chat",
                json={"model": model, "think": False, "stream": False,
                      "format": "json",
                      "messages": [
                          {"role": "system", "content": SLICE_SYSTEM},
                          {"role": "user", "content": user,
                           "images": [base64.b64encode(frame).decode()]}],
                      "options": {"temperature": 0, "num_predict": 128}},
                timeout=120.0)
            r.raise_for_status()
            parsed = _parse_slice(
                r.json().get("message", {}).get("content", ""))
            parsed.update(start=start, end=end)
            out.append(parsed)
        except (score_mod.OllamaError, MediaError):
            continue  # bad slice: skip, keep the rest
        except Exception:
            continue
        finally:
            if progress:
                progress(i + 1, len(bounds))
    try:
        _cache_path(fp, model).write_text(
            json.dumps({"fp": fp, "slices": out}), encoding="utf-8")
    except OSError:
        pass
    return {"slices": out, "source": "vision", "model": model}
