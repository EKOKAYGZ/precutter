"""Render trimmed video by concatenating keep-segments with ffmpeg."""
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from . import config
from .media import MediaError

Segment = Tuple[float, float]


def _build_filter(segments: List[Segment], audio_tracks: int = 1) -> str:
    """Build a filter_complex string that trims and concatenates segments.

    Every audio track gets the same trims so multi-track recordings keep all
    tracks in sync. audio_tracks=0 means video-only.
    """
    parts: List[str] = []
    for index, (start, end) in enumerate(segments):
        parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}]"
        )
        for track in range(audio_tracks):
            parts.append(
                f"[0:a:{track}]atrim=start={start:.3f}:end={end:.3f},"
                f"asetpts=PTS-STARTPTS[a{index}t{track}]"
            )
    count = len(segments)
    vinputs = "".join(f"[v{i}]" for i in range(count))
    if audio_tracks <= 0:
        parts.append(f"{vinputs}concat=n={count}:v=1:a=0[outv]")
        return ";".join(parts)
    parts.append(f"{vinputs}concat=n={count}:v=1:a=0[outv]")
    for track in range(audio_tracks):
        ainputs = "".join(f"[a{i}t{track}]" for i in range(count))
        parts.append(f"{ainputs}concat=n={count}:v=0:a=1[outa{track}]")
    return ";".join(parts)


def _run_ffmpeg(cmd: List[str]) -> None:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as exc:
        raise MediaError("ffmpeg not found. Install ffmpeg and add it to PATH.") from exc
    if result.returncode != 0:
        raise MediaError(f"ffmpeg render failed: {result.stderr.strip() or 'unknown error'}")


def _render_batch(
    input_path: Path, segments: List[Segment], output_path: Path, audio_tracks: int
) -> None:
    filter_complex = _build_filter(segments, audio_tracks)
    cmd = [
        config.FFMPEG_BIN,
        "-hide_banner",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[outv]",
    ]
    for track in range(audio_tracks):
        cmd += ["-map", f"[outa{track}]"]
    if audio_tracks > 0:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run_ffmpeg(cmd)


def _concat_batches(batches: List[Path], output_path: Path) -> None:
    """Concatenate intermediate files using the concat demuxer."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        for batch in batches:
            safe = str(batch).replace("'", "'\\''")
            handle.write(f"file '{safe}'\n")
        list_path = Path(handle.name)
    try:
        cmd = [
            config.FFMPEG_BIN,
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        _run_ffmpeg(cmd)
    finally:
        list_path.unlink(missing_ok=True)


def render(
    input_path: Path, segments: List[Segment], output_path: Path, audio_tracks: int = 1
) -> None:
    """Render segments into output_path, batching if there are many segments."""
    if not segments:
        raise MediaError("No segments to render.")
    if audio_tracks < 0:
        raise MediaError(f"Invalid audio track count: {audio_tracks}.")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    batch_size = config.MAX_SEGMENTS_PER_BATCH
    if len(segments) <= batch_size:
        _render_batch(input_path, segments, output_path, audio_tracks)
        return

    with tempfile.TemporaryDirectory(prefix="precutter_") as tmp:
        tmp_dir = Path(tmp)
        batches: List[Path] = []
        for index in range(0, len(segments), batch_size):
            batch = segments[index : index + batch_size]
            batch_path = tmp_dir / f"batch_{index // batch_size:04d}.mp4"
            _render_batch(input_path, batch, batch_path, audio_tracks)
            batches.append(batch_path)
        _concat_batches(batches, output_path)