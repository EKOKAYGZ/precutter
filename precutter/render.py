"""Render trimmed video by encoding keep-segments separately, then joining.

Why not one big filter_complex (trim/atrim x N + concat)? That builds a
single graph with 3*N filter chains on the same input. Past ~50-100
segments ffmpeg's scheduler stalls (no frames flow, empty output). Encoding
each segment with its own trivial graph and joining with the concat demuxer
(`-c copy`, all parts share codec settings) scales to any segment count and
keeps every audio track automatically.
"""
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from . import config
from .media import MediaError, has_audio_stream, preferred_video_encoder, has_audio_stream

Segment = Tuple[float, float]

# Fast-seek anchor before the exact cut point (input seeking is keyframe-based
# and fast; the small remainder uses accurate output seeking).
SEEK_PAD = 2.0


def _segment_cmd(input_path: Path, start: float, duration: float,
                 output_path: Path, with_audio: bool) -> List[str]:
    """One ffmpeg invocation cutting a single [start, start+duration) range."""
    base = max(0.0, start - SEEK_PAD)
    offset = start - base
    cmd = [
        config.FFMPEG_BIN,
        "-hide_banner",
        "-y",
        "-ss",
        f"{base:.3f}",
        "-i",
        str(input_path),
        "-ss",
        f"{offset:.3f}",
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v",
    ]
    if with_audio:
        cmd += ["-map", "0:a"]
    cmd += preferred_video_encoder()
    cmd += ["-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


def _run_ffmpeg(cmd: List[str]) -> None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as exc:
        raise MediaError("ffmpeg not found. Install ffmpeg and add it to PATH.") from exc
    if result.returncode != 0:
        raise MediaError(f"ffmpeg render failed: {result.stderr.strip() or 'unknown error'}")


def _concat_parts(parts: List[Path], output_path: Path) -> None:
    """Join same-codec parts with the concat demuxer (stream copy)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        for part in parts:
            safe = str(part).replace("'", "'\\''")
            handle.write(f"file '{safe}'\n")
        list_path = Path(handle.name)
    try:
        cmd = [
            config.FFMPEG_BIN,
            "-hide_banner",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        _run_ffmpeg(cmd)
    finally:
        list_path.unlink(missing_ok=True)


def render(input_path: Path, segments: List[Segment], output_path: Path,
           progress=None) -> None:
    """Render keep-segments into output_path. All audio tracks are preserved.

    progress, if given, is called as progress(done, total) after each part.
    """
    segments = [(s, e) for s, e in segments if e - s > 1e-6]
    if not segments:
        raise MediaError("No segments to render.")
    with_audio = has_audio_stream(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if len(segments) == 1:
        [(start, end)] = segments
        _run_ffmpeg(_segment_cmd(input_path, start, end - start, output_path, with_audio))
        if progress is not None:
            progress(1, 1)
        return

    with tempfile.TemporaryDirectory(prefix="precutter_") as tmp:
        parts: List[Path] = []
        for index, (start, end) in enumerate(segments):
            part_path = Path(tmp) / f"part_{index:05d}.mp4"
            _run_ffmpeg(_segment_cmd(input_path, start, end - start, part_path, with_audio))
            parts.append(part_path)
            if progress is not None:
                progress(index + 1, len(segments))
        _concat_parts(parts, output_path)
