"""Lightweight preview proxies: per-track audio + 720p video, built once.

Why: playing preview straight from a 3+ GB multi-track source means the
browser streams a huge file while <audio> elements get re-seeked on every
sync tick (audible gaps). Proxies are small, fast to read, and support
HTTP Range (seek works).

Writes are atomic (.part + os.replace) under per-file locks, so a player
never sees a half-written file — the race that used to serve truncated
audio ("ses yüklenemedi").
"""
import os
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional

from . import config, media

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def proxy_dir(stem: str) -> Path:
    d = config.WORKSPACE_DIR / "previews" / stem
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _atomic_replace(tmp: Path, final: Path) -> None:
    os.replace(tmp, final)


def build_track_audio(src: Path, track: int, outdir: Path) -> str:
    """trackN.ogg (opus 96k), fallback trackN.m4a (aac). Returns filename."""
    key = f"{outdir.name}:audio:{track}"
    with _lock_for(key):
        for suffix, codec, fmt in ((".ogg", "libopus", "ogg"),
                                   (".m4a", "aac", "mp4")):
            final = outdir / f"track{track}{suffix}"
            if final.exists() and final.stat().st_size > 1024:
                return final.name
            tmp = outdir / f"track{track}{suffix}.part"
            cmd = [config.FFMPEG_BIN, "-hide_banner", "-nostats", "-v", "error",
                   "-y", "-i", str(src), "-map", f"0:a:{track}", "-vn",
                   "-c:a", codec, "-b:a", "96k", "-ac", "2",
                   "-threads", "2", "-f", fmt, str(tmp)]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True)
            except (FileNotFoundError, OSError) as exc:
                raise media.MediaError(f"ffmpeg not found: {exc}") from exc
            if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1024:
                _atomic_replace(tmp, final)
                return final.name
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        raise media.MediaError(f"Could not build proxy audio for track {track}.")


def build_video_proxy(src: Path, outdir: Path,
                      height: int = 720) -> Optional[str]:
    """720p H.264 proxy (no audio). Returns filename or None when skipped."""
    key = f"{outdir.name}:video"
    with _lock_for(key):
        final = outdir / "proxy.mp4"
        if final.exists() and final.stat().st_size > 1024:
            return final.name
        tmp = outdir / "proxy.mp4.part"
        cmd = [config.FFMPEG_BIN, "-hide_banner", "-nostats", "-v", "error",
               "-y", "-i", str(src),
               "-vf", f"scale=-2:{height}", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "28", "-an",
               "-threads", "4",
               "-movflags", "+faststart", "-f", "mp4", str(tmp)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except (FileNotFoundError, OSError) as exc:
            raise media.MediaError(f"ffmpeg not found: {exc}") from exc
        if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1024:
            _atomic_replace(tmp, final)
            return final.name
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def status(stem: str, tracks: List[int]) -> dict:
    """What proxy files exist right now (no building)."""
    outdir = config.WORKSPACE_DIR / "previews" / stem
    audio: Dict[int, str] = {}
    for t in tracks:
        for suffix in (".ogg", ".m4a"):
            cand = outdir / f"track{t}{suffix}"
            if cand.exists() and cand.stat().st_size > 1024:
                audio[t] = cand.name
                break
    video = None
    cand = outdir / "proxy.mp4"
    if cand.exists() and cand.stat().st_size > 1024:
        video = cand.name
    ready = len(audio) == len(tracks)
    return {"ready": ready, "audio": audio, "video": video}
