"""Silence detection using ffmpeg's silencedetect filter."""
import re
import subprocess
from pathlib import Path
from typing import List, Tuple

from . import config
from .media import MediaError

# Matches ffmpeg silencedetect log lines on stderr.
_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")


def detect_silence(
    path: Path,
    threshold_db: float = config.THRESHOLD_DB,
    min_silence: float = config.MIN_SILENCE,
    duration: float | None = None,
    audio_track: int = 0,
    channel: int | None = None,
    sample_seconds: float | None = None,
) -> List[Tuple[float, float]]:
    """Run silencedetect and return a list of (start, end) silence intervals.

    audio_track selects `-map 0:a:<track>` (multi-track recordings, e.g. OBS
    mic/game tracks). channel isolates one stereo channel first via
    `pan=mono|c0=c<channel>` (e.g. mic on left, game on right).
    sample_seconds limits analysis to the first N seconds (fast activity scan).
    """
    if audio_track < 0:
        raise MediaError(f"Invalid audio track: {audio_track}.")
    if channel is not None and channel < 0:
        raise MediaError(f"Invalid audio channel: {channel}.")
    filt = f"silencedetect=noise={threshold_db}dB:d={min_silence}"
    if channel is not None:
        filt = f"pan=mono|c0=c{channel},{filt}"
    cmd = [
        config.FFMPEG_BIN,
        "-hide_banner",
        "-nostats",
    ]
    if sample_seconds is not None and sample_seconds > 0:
        cmd += ["-t", f"{sample_seconds:.3f}"]
    cmd += [
        "-i",
        str(path),
        "-map",
        f"0:a:{audio_track}",
        "-af",
        filt,
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as exc:
        raise MediaError("ffmpeg not found. Install ffmpeg and add it to PATH.") from exc

    stderr = result.stderr or ""
    if result.returncode != 0 and "silence" not in stderr.lower():
        raise MediaError(f"silencedetect failed: {stderr.strip() or 'unknown error'}")

    silences = _parse_silences(stderr, duration)
    return silences


def _parse_silences(stderr: str, duration: float | None) -> List[Tuple[float, float]]:
    """Parse silence_start/silence_end pairs, closing trailing silence."""
    silences: List[Tuple[float, float]] = []
    current_start: float | None = None
    for line in stderr.splitlines():
        start_match = _START_RE.search(line)
        if start_match:
            current_start = float(start_match.group(1))
            continue
        end_match = _END_RE.search(line)
        if end_match and current_start is not None:
            end = float(end_match.group(1))
            silences.append((max(current_start, 0.0), max(end, 0.0)))
            current_start = None

    # Trailing silence with no end -> close at media duration.
    if current_start is not None:
        end = duration if duration is not None else current_start
        if duration is not None:
            silences.append((max(current_start, 0.0), max(end, 0.0)))

    silences.sort(key=lambda pair: pair[0])
    return silences