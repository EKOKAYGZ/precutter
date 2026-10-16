"""Render trimmed video by joining keep-segments with sample-accurate audio.

Pipeline (multi-track safe):
  1. Each keep-segment is cut to a `.mkv` intermediate carrying video plus
     EVERY audio track as PCM (`pcm_s16le`). PCM has no encoder priming, so
     joins are sample-exact — unlike per-part AAC, which adds ~20 ms of
     padding at every join and drifts out of sync.
  2. Intermediates are joined with the concat demuxer (`-c copy`, `-map 0`).
  3. ONE final pass copies the video and encodes each audio track to AAC
     once, restoring per-track language/title metadata from the source.

Why not one big filter_complex (trim/atrim x N + concat)? Past ~50-100
segments ffmpeg's scheduler stalls (no frames flow, empty output).
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import config
from .media import MediaError, preferred_video_encoder

Segment = Tuple[float, float]
ProgressFn = Callable[[int, int], None]

# Mixdown: mic track is boosted so speech stays intelligible over game audio.
MIX_MIC_VOLUME = 1.5

# Fast-seek anchor before the exact cut point (input seeking is keyframe-based
# and fast; exact bounds come from trim/atrim filters, never output -ss/-t).
SEEK_PAD = 2.0


def _seek_base(start: float) -> float:
    """Input-seek anchor, rounded exactly as passed to ffmpeg.

    The offset below is computed from this same value so both sides agree
    bit-for-bit (strtod round-trips the %.3f form exactly).
    """
    return round(max(0.0, start - SEEK_PAD), 3)


def _bounds(offset: float, duration: float) -> tuple[str, str]:
    """Exact trim bounds, relative to the input-seek point.

    Input `-ss` rebases filter timestamps to 0 (verified empirically), while
    output `-ss` leaves filters seeing unshifted times — so cutting uses
    input-seek + trim filters only, never output `-ss`/`-t`.
    Margins absorb float formatting noise: 0.2 ms early at the start (a
    neighboring frame is >= 8 ms away) and 0.1 ms early at the end, costing
    at most ~0.1 ms of audio per part — inaudible and drift-free.
    """
    return f"{offset - 0.0002:.6f}", f"{offset + duration - 0.0001:.6f}"


def _segment_cmd(input_path: Path, start: float, duration: float,
                 output_path: Path, with_audio: bool,
                 vargs: Optional[List[str]] = None) -> List[str]:
    """Cut one [start, start+duration) range to a .mkv intermediate.

    Audio (all tracks) is stored as PCM so later joins stay sample-accurate.
    """
    base = _seek_base(start)
    trim_start, trim_end = _bounds(start - base, duration)
    cmd = [
        config.FFMPEG_BIN,
        "-hide_banner",
        "-y",
        "-ss",
        f"{base:.3f}",
        "-i",
        str(input_path),
        "-vf",
        f"trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS",
        "-map",
        "0:v:0",
    ]
    if with_audio:
        cmd += ["-map", "0:a?"]
    cmd += vargs if vargs is not None else preferred_video_encoder()
    cmd += ["-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-af", f"atrim=start={trim_start}:end={trim_end},asetpts=PTS-STARTPTS"]
        cmd += ["-c:a", "pcm_s16le"]
    cmd += [str(output_path)]
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
    """Join same-codec parts with the concat demuxer. `-map 0` keeps every
    video/audio track (without it ffmpeg's default selection drops all but
    one audio track)."""
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
            "-map", "0",
            "-map_metadata", "0",
            "-c", "copy",
            str(output_path),
        ]
        _run_ffmpeg(cmd)
    finally:
        list_path.unlink(missing_ok=True)


def _audio_outputs(tracks: List[dict], mic_track: int, mode: str,
                   trim: Optional[Tuple[str, str]] = None):
    """Final audio stage for one input: (filter_complex|None, maps, meta_args).

    trim=(start,end) cuts every output with atrim first (single-pass from the
    full source); None skips trimming (final mux of already-exact parts).
    Modes (output order + dispositions):
    - "mix": [mixed(mic-boosted, default)] + originals (not default).
    - "separate": originals, mic is default.
    - "miconly": mic track only, default.
    """
    n = len(tracks)
    if n == 0:
        return None, [], []
    mic = mic_track if 0 <= mic_track < n else 0
    # Unknown modes fall back to "separate" (keep everything, mic default).
    if mode not in ("mix", "separate", "miconly"):
        mode = "separate"
    chains: List[str] = []
    maps: List[str] = []
    meta: List[str] = []

    def _trimmed(src: int, label: str, extra: str = "") -> str:
        steps = []
        if trim is not None:
            steps.append(f"atrim=start={trim[0]}:end={trim[1]},asetpts")
        if extra:
            steps.append(extra)
        if not steps:
            steps.append("anull")
        return f"[0:a:{src}]{','.join(steps)}[{label}]"

    def _meta(index: int, track: dict, default: bool) -> None:
        language = track.get("language") or "und"
        meta.extend(["-metadata:s:a:{0}".format(index),
                     f"language={language}"])
        title = (track.get("title") or "").strip()
        if title and title.lower() not in ("soundhandler", "audiohandler"):
            meta.extend(["-metadata:s:a:{0}".format(index), f"title={title}"])
        meta.extend(["-disposition:a:{0}".format(index),
                     "default" if default else "0"])

    if mode == "mix":
        for i in range(n):
            vol = MIX_MIC_VOLUME if i == mic else 1.0
            chains.append(_trimmed(i, f"m{i}", extra=f"volume={vol}"))
        chains.append("".join(f"[m{i}]" for i in range(n))
                      + f"amix=inputs={n}:normalize=0[mixout]")
        maps.append("[mixout]")
        meta.extend(["-metadata:s:a:0", "title=Mix",
                     "-metadata:s:a:0",
                     f"language={tracks[mic].get('language') or 'und'}",
                     "-disposition:a:0", "default"])
    order = list(range(n)) if mode in ("mix", "separate") else [mic]
    for out_index, src in enumerate(order, start=(1 if mode == "mix" else 0)):
        chains.append(_trimmed(src, f"ao{out_index}"))
        maps.append(f"[ao{out_index}]")
        _meta(out_index, tracks[src], default=(src == mic))
    filt = ";".join(chains) if chains else None
    return filt, maps, meta


def _final_mux_cmd(joined_path: Path, output_path: Path,
                   tracks: List[dict], with_audio: bool,
                   mic_track: int = 0, mode: str = "mix") -> List[str]:
    """Single final pass: copy video, encode each audio track to AAC once."""
    cmd = [
        config.FFMPEG_BIN,
        "-hide_banner",
        "-y",
        "-i",
        str(joined_path),
        "-map",
        "0:v:0",
    ]
    filt, maps, meta = _audio_outputs(tracks, mic_track, mode) if with_audio else (None, [], [])
    if filt:
        cmd += ["-filter_complex", filt]
    for m in maps:
        cmd += ["-map", m]
    cmd += ["-map_metadata", "0", "-c:v", "copy"]
    if maps:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += meta
    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


def _single_pass_cmd(input_path: Path, start: float, duration: float,
                     output_path: Path, tracks: List[dict], with_audio: bool,
                     vargs: Optional[List[str]] = None,
                     mic_track: int = 0, mode: str = "mix") -> List[str]:
    """Direct one-segment render (no intermediates needed)."""
    base = _seek_base(start)
    trim_start, trim_end = _bounds(start - base, duration)
    cmd = [
        config.FFMPEG_BIN,
        "-hide_banner",
        "-y",
        "-ss",
        f"{base:.3f}",
        "-i",
        str(input_path),
        "-vf",
        f"trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS",
        "-map",
        "0:v:0",
    ]
    filt, maps, meta = (
        _audio_outputs(tracks, mic_track, mode, trim=(trim_start, trim_end))
        if with_audio else (None, [], [])
    )
    if filt:
        cmd += ["-filter_complex", filt]
    for m in maps:
        cmd += ["-map", m]
    cmd += ["-map_metadata", "0"]
    cmd += vargs if vargs is not None else preferred_video_encoder()
    cmd += ["-pix_fmt", "yuv420p"]
    if maps:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += meta
    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


def check_free_space(input_path: Path, segments: List[Segment],
                     output_path: Path, tracks: List[dict]) -> None:
    """Fail fast when the disk clearly cannot hold intermediates + output.

    PCM intermediates dominate: kept_seconds × 48 kHz × 2 ch × 2 bytes per
    track, plus a re-encoded copy of the source scaled to the kept fraction.
    """
    kept = sum(e - s for s, e in segments)
    video_part = 0.0
    try:
        from . import media as _media

        src_dur = max(_media.get_duration(input_path), 1e-6)
        video_part = input_path.stat().st_size * (kept / src_dur) * 1.5
    except (OSError, MediaError):
        pass
    pcm_bytes = 0.0
    for track in tracks:
        channels = track.get("channels") or 2
        pcm_bytes += kept * 48000 * channels * 2
    need = video_part + pcm_bytes + 512 * 1024 * 1024
    try:
        free = shutil.disk_usage(output_path.parent).free
    except OSError:
        return
    if free < need:
        raise MediaError(
            f"Not enough disk space: need ~{need / 1024**3:.1f} GB, "
            f"have {free / 1024**3:.1f} GB free."
        )


def render(input_path: Path, segments: List[Segment], output_path: Path,
           progress: Optional[ProgressFn] = None,
           mic_track: int = 0, output_audio: Optional[str] = None) -> None:
    """Render keep-segments into output_path, preserving every audio track.

    progress, if given, is called as progress(done, total) as work completes.
    mic_track selects the reference (microphone) track for mixing and the
    default disposition. output_audio is "mix" (default), "separate" or
    "miconly"; None reads the server setting.
    """
    from . import media as _media

    segments = [(s, e) for s, e in segments if e - s > 1e-6]
    if not segments:
        raise MediaError("No segments to render.")
    try:
        tracks = _media.audio_streams(input_path, include_loudness=False)
    except MediaError:
        tracks = []
    with_audio = len(tracks) > 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    check_free_space(input_path, segments, output_path, tracks if with_audio else [])

    mode = output_audio or getattr(config, "OUTPUT_AUDIO", "mix")
    bitrate = _media.get_video_bitrate(input_path)
    vargs = _media.preferred_video_encoder(bitrate_bps=bitrate)

    if len(segments) == 1:
        [(start, end)] = segments
        _run_ffmpeg(_single_pass_cmd(
            input_path, start, end - start, output_path, tracks, with_audio,
            vargs, mic_track, mode))
        if progress is not None:
            progress(1, 1)
        return

    total = len(segments)
    with tempfile.TemporaryDirectory(prefix="precutter_") as tmp:
        parts: List[Path] = []
        for index, (start, end) in enumerate(segments):
            part_path = Path(tmp) / f"part_{index:05d}.mkv"
            _run_ffmpeg(_segment_cmd(
                input_path, start, end - start, part_path, with_audio, vargs))
            parts.append(part_path)
            if progress is not None:
                progress(index + 1, total)
        joined = Path(tmp) / "joined.mkv"
        _concat_parts(parts, joined)
        # PCM parçalar GB'larca tutabilir; birleştirme bitince hemen sil.
        for part_path in parts:
            part_path.unlink(missing_ok=True)
        _run_ffmpeg(_final_mux_cmd(joined, output_path, tracks, with_audio, mic_track, mode))
        if progress is not None:
            progress(total, total)
