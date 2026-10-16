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


def get_fps(path: Path) -> float:
    """Return the source video frame rate (frames per second)."""
    info = _run_ffprobe(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        raw = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or ""
        try:
            num, den = raw.split("/")
            fps = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            continue
        if fps > 0:
            return fps
    raise MediaError("Could not determine video frame rate.")


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
        # OBS track names live in `name`; fall back through title/handler.
        title = (
            tags.get("title") or tags.get("name")
            or tags.get("handler_name") or ""
        )
        levels = track_levels(path, len(tracks)) if include_loudness else None
        tracks.append(
            {
                "track": len(tracks),
                "channels": channels,
                "codec": stream.get("codec_name", "unknown"),
                "language": tags.get("language", "und"),
                "title": title,
                "loudness_db": levels["mean_db"] if levels else None,
                "max_db": levels["max_db"] if levels else None,
            }
        )
    return tracks


def suggest_mic_track(tracks: List[Dict[str, Any]]) -> Optional[int]:
    """Hangi ses izinin mikrofona benzediğini tahmin eder (0-based track).

    Öncelik: başlığında "mic"/"mikrofon" geçen iz kazanır. Yoksa, ortalama
    sesi en düşük olan iz seçilir: sürekli oyun sesi yüksek ve sabittir,
    aralıklı konuşma ise ortalamayı düşürür. Tek iz varsa o döner, fark
    belirsizse ya da ölçüm yoksa None döner.
    """
    if not tracks:
        return None
    if len(tracks) == 1:
        return int(tracks[0].get("track", 0))
    for t in tracks:
        title = str(t.get("title", "")).lower()
        if "mic" in title or "mikrofon" in title or "voice" in title:
            return int(t.get("track", 0))
    measured = [
        (float(t["loudness_db"]), int(t.get("track", 0)))
        for t in tracks
        if t.get("loudness_db") is not None
    ]
    if not measured:
        return None
    measured.sort()
    if len(measured) > 1 and measured[1][0] - measured[0][0] < 1.0:
        return None  # fark belirsiz, yanlış tahminden iyidir
    return measured[0][1]


_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")
_MAX_VOLUME_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?|n/a)\s*dB", re.IGNORECASE)

_ENCODER_CACHE: dict = {}


def get_video_bitrate(path: Path) -> Optional[int]:
    """Source video bit rate in bits/sec (stream bit_rate, else format)."""
    try:
        info = _run_ffprobe(path)
    except MediaError:
        return None
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video" and stream.get("bit_rate"):
            try:
                return int(stream["bit_rate"])
            except (TypeError, ValueError):
                pass
    try:
        return int(info.get("format", {}).get("bit_rate"))
    except (TypeError, ValueError):
        return None


def preferred_video_encoder(
    quality: Optional[str] = None, bitrate_bps: Optional[int] = None
) -> List[str]:
    """H264 encoder args for the requested quality mode.

    - "match" (default): target the source bitrate (-b:v), capped at 1.5x
      with -maxrate (NVENC: -rc vbr), so output size tracks the source.
    - "high": fixed high quality (NVENC CQ 20 / x264 CRF 20).
    - "small": fixed small files (NVENC CQ 28 / x264 CRF 26).
    Unknown bitrate falls back to "high" behavior. Cached per (pref, mode).
    """
    if quality is None:
        quality = getattr(config, "QUALITY", "match")
    pref = getattr(config, "ENCODER_PREF", "auto")
    cache_key = (pref, quality, bitrate_bps if quality == "match" else None)
    if cache_key in _ENCODER_CACHE:
        return _ENCODER_CACHE[cache_key]
    if pref == "x264":
        nvenc = False
    elif pref == "nvenc":
        nvenc = True
    else:
        try:
            result = subprocess.run(
                [config.FFMPEG_BIN, "-hide_banner", "-encoders"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            nvenc = result.returncode == 0 and "h264_nvenc" in (result.stdout or "")
        except (FileNotFoundError, OSError):
            nvenc = False
    if quality == "match" and bitrate_bps:
        target_k = max(int(bitrate_bps // 1000), 500)
        max_k = int(target_k * 1.5)
        buf_k = max_k * 2
        if nvenc:
            args = ["-c:v", "h264_nvenc", "-preset", "p4",
                    "-rc", "vbr", "-b:v", f"{target_k}k",
                    "-maxrate", f"{max_k}k", "-bufsize", f"{buf_k}k"]
        else:
            args = ["-c:v", "libx264", "-preset", "veryfast",
                    "-b:v", f"{target_k}k",
                    "-maxrate", f"{max_k}k", "-bufsize", f"{buf_k}k"]
    elif quality == "small":
        args = (["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "28"]
                if nvenc else
                ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26"])
    else:
        args = (["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"]
                if nvenc else
                ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])
    _ENCODER_CACHE[cache_key] = args
    # Legacy single-key entry kept for backward compatibility.
    _ENCODER_CACHE.setdefault("args", args)
    return args


def encoder_name() -> str:
    """'nvenc' veya 'x264' — /health ve kayıtlar için."""
    return "nvenc" if "nvenc" in preferred_video_encoder()[1] else "x264"


def _volumedetect_stderr(path: Path, track: int) -> Optional[str]:
    """Tek iz için volumedetect çıktısı (stderr). ffmpeg yoksa None."""
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
    return result.stderr or ""


def track_levels(path: Path, track: int) -> Dict[str, Optional[float]]:
    """Tek volumedetect çalışmasıyla ortalama + tepe ses (dB).

    Döner: {"mean_db": ..., "max_db": ...}; ölçülemeyen değer None olur.
    """
    stderr = _volumedetect_stderr(path, track)
    out: Dict[str, Optional[float]] = {"mean_db": None, "max_db": None}
    if stderr is None:
        return out
    mean_match = _MEAN_VOLUME_RE.search(stderr)
    if mean_match:
        try:
            out["mean_db"] = round(float(mean_match.group(1)), 1)
        except ValueError:
            pass
    max_match = _MAX_VOLUME_RE.search(stderr)
    if max_match and max_match.group(1).lower() != "n/a":
        try:
            out["max_db"] = round(float(max_match.group(1)), 1)
        except ValueError:
            pass
    return out


def track_loudness(path: Path, track: int) -> Optional[float]:
    """Mean volume (dB) of one audio track via volumedetect. Fast, no encode.

    Returns None when ffmpeg is missing or the value can't be parsed.
    Helps users tell mic and game tracks apart in the source picker.
    """
    return track_levels(path, track)["mean_db"]


def track_max_volume(path: Path, track: int) -> Optional[float]:
    """Aynı volumedetect çıktısından tepe ses (dB). Ölçülemezse None."""
    return track_levels(path, track)["max_db"]


def track_silence_activity(
    path: Path,
    track: int,
    threshold_db: float = config.THRESHOLD_DB,
    min_silence: float = 0.3,
    sample_seconds: float = 180.0,
) -> Dict[str, float]:
    """Speech-like on/off ölçümü: ilk N saniyedeki sessizlik oranı + geçiş sayısı.

    Sürekli oyun sesi ~0 geçiş verir; aralıklı konuşma (mikrofon) çok geçiş
    ve dengeli sessizlik oranı verir. Hiç ses yoksa da 0 geçiş verir.
    """
    from . import silence as _silence

    try:
        duration = get_duration(path)
    except MediaError:
        return {"silence_ratio": 0.0, "transitions": 0, "window": 0.0}
    window = min(sample_seconds, duration)
    if window <= 0:
        return {"silence_ratio": 0.0, "transitions": 0, "window": 0.0}
    try:
        sils = _silence.detect_silence(
            path, threshold_db, min_silence, window,
            audio_track=track, sample_seconds=window,
        )
    except MediaError:
        return {"silence_ratio": 0.0, "transitions": 0, "window": window}
    sil_time = sum(min(e, window) - max(s, 0.0) for s, e in sils)
    sil_time = max(0.0, min(sil_time, window))
    return {
        "silence_ratio": round(sil_time / window, 4),
        "transitions": 2 * len(sils),
        "window": round(window, 3),
    }


def score_track_activity(
    transitions: int, silence_ratio: float, dyn_range_db: Optional[float] = None
) -> float:
    """Konuşma-benzeri aktivite puanı (0-1). Saf fonksiyon, test edilebilir.

    dyn_range_db (max-mean dB) verilirse dinamik aralık da hesaba katılır:
    sürekli oyun sesi dar aralıklıdır, konuşma geniştir.
    """
    if transitions < 4:
        return 0.0
    if not 0.05 < silence_ratio < 0.95:
        return 0.0
    pattern = min(transitions / 20.0, 1.0)
    balance = 1.0 - abs(silence_ratio - 0.5) * 2.0
    score = 0.6 * pattern + 0.4 * max(balance, 0.0)
    if dyn_range_db is not None:
        dyn = min(max(dyn_range_db, 0.0) / 24.0, 1.0)
        score = 0.4 * pattern + 0.3 * max(balance, 0.0) + 0.3 * dyn
    return round(score, 3)


def suggest_mic_with_confidence(
    path: Path,
    tracks: List[Dict[str, Any]],
    threshold_db: float = config.THRESHOLD_DB,
    min_silence: float = 0.3,
) -> Optional[Dict[str, Any]]:
    """Mikrofon izi tahmini + güven (0-1). Her zaman bir öneri döner.

    Önce her izin konuşma-benzeri açma/kapama örüntüsüne bakılır; skor
    çıkmazsa başlık/ses-seviyesi sezgiseline, o da olmazsa OBS tarzı
    2 izli dosyalarda son ize düşülür.
    """
    if not tracks:
        return None
    if len(tracks) == 1:
        return {"track": int(tracks[0].get("track", 0)), "confidence": 0.5}
    scored = []
    for track in tracks:
        activity = track_silence_activity(
            path, int(track.get("track", 0)), threshold_db, min_silence
        )
        dyn = None
        if track.get("max_db") is not None and track.get("loudness_db") is not None:
            dyn = float(track["max_db"]) - float(track["loudness_db"])
        score = score_track_activity(
            int(activity["transitions"]), float(activity["silence_ratio"]), dyn
        )
        scored.append((score, int(track.get("track", 0))))
    scored.sort(reverse=True)
    if scored[0][0] > 0:
        return {
            "track": scored[0][1],
            "confidence": round(min(0.5 + scored[0][0] / 2.0, 0.95), 2),
        }
    legacy = suggest_mic_track(tracks)
    if legacy is not None:
        return {"track": legacy, "confidence": 0.4}
    if len(tracks) == 2:
        return {"track": int(tracks[-1].get("track", 1)), "confidence": 0.3}
    return {"track": int(tracks[0].get("track", 0)), "confidence": 0.2}