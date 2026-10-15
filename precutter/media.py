"""Media probing and ffmpeg/ffprobe availability checks."""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config


class MediaError(Exception):
    """Raised when a media operation fails."""


def _tool_exists(name: str) -> bool:
    return shutil.which(name) is not None


def check_tools() -> None:
    """Verify ffmpeg and ffprobe are installed and reachable."""
    missing = [name for name in (config.FFMPEG_BIN, config.FFPROBE_BIN) if not _tool_exists(name)]
    if missing:
        raise MediaError(
            "Missing required tool(s): "
            + ", ".join(missing)
            + ". Install ffmpeg and ensure it is on your PATH."
        )


def _run_ffprobe(path: Path) -> dict[str, Any]:
    cmd = [
        config.FFPROBE_BIN,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as exc:
        raise MediaError("ffprobe not found. Install ffmpeg and add it to PATH.") from exc
    if result.returncode != 0:
        raise MediaError(f"ffprobe failed: {result.stderr.strip() or 'unknown error'}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError("Could not parse ffprobe output.") from exc


def get_duration(path: Path) -> float:
    """Return the duration of a media file in seconds."""
    if not path.exists():
        raise MediaError(f"File not found: {path}")
    info = _run_ffprobe(path)
    duration = info.get("format", {}).get("duration")
    if duration is None:
        # Fall back to a stream duration.
        for stream in info.get("streams", []):
            if stream.get("duration") is not None:
                duration = stream["duration"]
                break
    if duration is None:
        raise MediaError("Could not determine media duration.")
    try:
        return float(duration)
    except (TypeError, ValueError) as exc:
        raise MediaError(f"Invalid duration value: {duration}") from exc


def has_video_stream(path: Path) -> bool:
    """Return True if the file contains at least one video stream."""
    info = _run_ffprobe(path)
    return any(stream.get("codec_type") == "video" for stream in info.get("streams", []))


def has_audio_stream(path: Path) -> bool:
    """Return True if the file contains at least one audio stream."""
    info = _run_ffprobe(path)
    return any(stream.get("codec_type") == "audio" for stream in info.get("streams", []))


def audio_streams(path: Path, include_loudness: bool = True) -> List[Dict[str, Any]]:
    """Describe audio streams: track (0-based for `-map 0:a:<track>`), channels, codec, language, title."""
    info = _run_ffprobe(path)
    tracks: List[Dict[str, Any]] = []
    for stream in info.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        tags = stream.get("tags", {}) or {}
        try:
            channels = int(stream.get("channels", 0))
        except (TypeError, ValueError):
            channels = 0
        tracks.append(
            {
                "track": len(tracks),
                "channels": channels,
                "codec": stream.get("codec_name", "unknown"),
                "language": tags.get("language", "und"),
                "title": tags.get("title", ""),
                "loudness_db": track_loudness(path, len(tracks)) if include_loudness else None,
            }
        )
    return tracks


_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")

_ENCODER_CACHE: dict = {}


def preferred_video_encoder() -> List[str]:
    """H264 encoder args: NVENC (donanım) varsa onu kullan, yoksa libx264.

    NVENC yeniden kodlamayı ~5-10x hızlandırır; kalite eşdeğeri korunur
    (nvenc CQ 20 ~= x264 CRF 20). Sonuç önbelleğe alınır (tek ffmpeg çağrısı).
    """
    if "args" in _ENCODER_CACHE:
        return _ENCODER_CACHE["args"]
    try:
        result = subprocess.run(
            [config.FFMPEG_BIN, "-hide_banner", "-encoders"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        nvenc = result.returncode == 0 and "h264_nvenc" in (result.stdout or "")
    except (FileNotFoundError, OSError):
        nvenc = False
    args = (
        ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"]
        if nvenc
        else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    )
    _ENCODER_CACHE["args"] = args
    return args


def encoder_name() -> str:
    """'nvenc' veya 'x264' — /health ve loglar için."""
    return "nvenc" if "nvenc" in preferred_video_encoder()[1] else "x264"


def track_loudness(path: Path, track: int) -> Optional[float]:
    """Mean volume (dB) of one audio track via volumedetect. Fast, no encode.

    Returns None when ffmpeg is missing or the value can't be parsed.
    Helps users tell mic and game tracks apart in the source picker.
    """
    cmd = [
        config.FFMPEG_BIN,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-map",
        f"0:a:{track}",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except (FileNotFoundError, OSError):
        return None
    match = _MEAN_VOLUME_RE.search(result.stderr or "")
    if not match:
        return None
    try:
        return round(float(match.group(1)), 1)
    except ValueError:
        return None