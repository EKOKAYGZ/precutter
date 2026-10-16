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


def _low_priority_flags() -> int:
    """Windows'ta ffmpeg'i normal-altı önceliğe al: analiz CPU'yu kapsın."""
    if os.name == "nt":
        return getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    return 0


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
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    creationflags=_low_priority_flags())
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
                      height: int = 720,
                      duration: Optional[float] = None,
                      progress=None) -> Optional[str]:
    """720p H.264 proxy (no audio). Returns filename or None when skipped.

    progress, verilirse progress(frac) ile 0..1 arası çağrılır (ffmpeg
    -progress çıktısından). Uzun kodlamada yüzde donmuş görünmez.
    """
    key = f"{outdir.name}:video"
    with _lock_for(key):
        final = outdir / "proxy.mp4"
        if final.exists() and final.stat().st_size > 1024:
            if progress is not None:
                progress(1.0)
            return final.name
        tmp = outdir / "proxy.mp4.part"
        cmd = [config.FFMPEG_BIN, "-hide_banner", "-nostats", "-v", "error",
               "-y", "-i", str(src),
               "-vf", f"scale=-2:{height}", "-c:v", "libx264",
               "-preset", "ultrafast", "-crf", "28", "-an",
               "-threads", "4",
               "-movflags", "+faststart",
               "-progress", "pipe:1", "-f", "mp4", str(tmp)]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
                creationflags=_low_priority_flags())
        except (FileNotFoundError, OSError) as exc:
            raise media.MediaError(f"ffmpeg not found: {exc}") from exc
        # ffmpeg'in "out_time_ms" alanı aslında MİKROsaniyedir (tarihsel
        # hata); "out_time_us" ile aynıdır. Süreyi de µs'e çevirip bölüyoruz.
        total_us = (duration * 1_000_000.0) if duration else 0.0
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if line == "progress=end":
                    break
                if total_us <= 0 or progress is None:
                    continue
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                    try:
                        us = float(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    progress(max(0.0, min(1.0, us / total_us)))
            proc.wait()
            rc = proc.returncode
        except (OSError, ValueError, AssertionError):
            try:
                proc.kill()
            except OSError:
                pass
            rc = 1
        if rc == 0 and tmp.exists() and tmp.stat().st_size > 1024:
            _atomic_replace(tmp, final)
            if progress is not None:
                progress(1.0)
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
