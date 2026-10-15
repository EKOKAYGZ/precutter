"""Media probing and ffmpeg/ffprobe availability checks."""
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

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


def audio_streams(path: Path) -> List[Dict[str, Any]]:
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
            }
        )
    return tracks