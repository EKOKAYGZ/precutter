"""Video frames: thumbnails for the vision model (content-aware cutting).

Optional layer: when no vision model is installed in Ollama, everything
falls back to transcript-only. Never downloads anything by itself.
"""
import base64
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from . import config
from .media import MediaError

FRAME_COUNT = 12
FRAME_WIDTH = 320


def extract_frames(path: Path, duration: float,
                   count: int = FRAME_COUNT,
                   width: int = FRAME_WIDTH) -> List[bytes]:
    """Spread `count` JPEG thumbnails across the video. Returns raw bytes."""
    if duration <= 0 or count <= 0:
        return []
    with tempfile.TemporaryDirectory(prefix="precutter-frames") as tmp:
        out = str(Path(tmp) / "f%02d.jpg")
        cmd = [config.FFMPEG_BIN, "-hide_banner", "-nostats", "-v", "error",
               "-i", str(path), "-vf",
               f"fps={count}/{duration:.3f},scale={width}:-1",
               "-q:v", "5", "-y", out]
        try:
            proc = subprocess.run(cmd, capture_output=True)
        except (FileNotFoundError, OSError) as exc:
            raise MediaError(f"ffmpeg not found: {exc}") from exc
        if proc.returncode != 0:
            raise MediaError("Could not extract frames.")
        files = sorted(Path(tmp).glob("f*.jpg"))
        return [p.read_bytes() for p in files[:count]]


def pick_vision_model(host: str, preference=None) -> Optional[str]:
    """First installed vision model, or None (no download, no error)."""
    from . import score as score_mod

    installed = score_mod.installed_models(host) or []
    for want in (preference or config.AI_VISION_MODELS):
        for name in installed:
            if name == want or name.startswith(want + ":"):
                return name
    return None


def _frames_key(fingerprint: str, model: str) -> str:
    import hashlib

    raw = f"{fingerprint}|{model}|frames-v1".encode()
    return "frames_" + hashlib.sha256(raw).hexdigest()[:32] + ".json"


def classify_content(path: Path, duration: float, fingerprint: str,
                     host: Optional[str] = None) -> Dict:
    """What is this video? {label, notes, model} — cached, optional vision.

    No vision model installed -> {"label": "general video", ...} fallback.
    """
    from . import score as score_mod
    from . import transcribe as transcribe_mod

    host = (host or config.OLLAMA_HOST or "http://127.0.0.1:11434").rstrip("/")
    vision = pick_vision_model(host)
    if vision is None:
        return {"label": "general video", "notes": "",
                "model": None}
    key = _frames_key(fingerprint, vision)
    cpath = transcribe_mod.cache_dir() / key
    try:
        cached = json.loads(cpath.read_text(encoding="utf-8"))
        if isinstance(cached, dict) and cached.get("fp") == fingerprint:
            return cached["result"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        frames = extract_frames(path, duration)
        images = [base64.b64encode(f).decode() for f in frames[:8]]
        import httpx

        r = httpx.post(
            f"{host}/api/chat",
            json={"model": vision, "think": False, "stream": False,
                  "format": "json",
                  "messages": [{
                      "role": "user",
                      "content": "What game or content is in these video frames? "
                                 'Reply JSON only: {"label":"short name, e.g. Minecraft",'
                                 ' "notes":"one line about style"}',
                      "images": images}]},
            timeout=120.0)
        r.raise_for_status()
        data = json.loads(r.json().get("message", {}).get("content", "{}"))
        result = {"label": str(data.get("label", "general video"))[:60],
                  "notes": str(data.get("notes", ""))[:200],
                  "model": vision}
    except Exception:
        result = {"label": "general video", "notes": "", "model": vision}
    try:
        cpath.write_text(json.dumps({"fp": fingerprint, "result": result}),
                         encoding="utf-8")
    except OSError:
        pass
    return result
