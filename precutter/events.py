"""v0.3 ses olayları: loudness eğrisi, spike tespiti, highlight adayları.

Modelsiz ve CPU-dostu: tek ffmpeg PCM decode + numpy. YAMNet/PANNs gibi
ağır sınıflandırıcılar isteğe bağlı gelecektir; bu modül kapalıyken bile
uygulama tam fonksiyoneldir (hata verirse analiz değil, sadece bu katman
boş döner).
"""
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config
from .media import MediaError

SR = 16000
BUCKET_MS = 100
_FLOOR_DB = -80.0


def loudness_curve(
    path: Path, audio_track: int = 0, sr: int = SR, bucket_ms: int = BUCKET_MS
) -> Tuple[List[float], List[float]]:
    """Mono PCM decode edip her bucket için RMS dB eğrisi döndürür.

    Returns (times, curve_db); sessizlik tabanı -80 dB'de kırpılır.
    """
    cmd = [
        config.FFMPEG_BIN, "-hide_banner", "-nostats", "-v", "error",
        "-i", str(path), "-map", f"0:a:{audio_track}",
        "-ac", "1", "-ar", str(sr), "-f", "s16le", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True)
    except (FileNotFoundError, OSError) as exc:
        raise MediaError(f"ffmpeg not found: {exc}") from exc
    if proc.returncode != 0 or not proc.stdout:
        raise MediaError("Could not read audio for event spotting.")
    try:
        import numpy as np
    except ImportError as exc:
        raise MediaError("numpy is required for event spotting.") from exc
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    per = max(1, int(sr * bucket_ms / 1000))
    n = len(samples) // per
    if n == 0:
        return [], []
    frames = samples[: n * per].reshape(n, per)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    curve = 20.0 * np.log10(np.maximum(rms, 1e-4))
    curve = np.maximum(curve, _FLOOR_DB)
    step = bucket_ms / 1000.0
    times = (np.arange(n) + 0.5) * step
    return [round(float(t), 3) for t in times], [round(float(v), 2) for v in curve]


def detect_spikes(
    times: List[float],
    curve_db: List[float],
    delta_db: float = 12.0,
    baseline_win_s: float = 5.0,
    min_gap_s: float = 1.0,
    floor_db: float = -50.0,
) -> List[Dict]:
    """Ani yükselişleri bul: geçmiş pencerenin medyanından `delta_db` üstü.

    Her spike {time, peak_db, delta_db}. Yakın patlamalarda en yüksek korunur.
    """
    if not times or len(times) != len(curve_db):
        return []
    try:
        import numpy as np
    except ImportError as exc:
        raise MediaError("numpy is required for event spotting.") from exc
    curve = np.asarray(curve_db, dtype=np.float64)
    step = max(1e-6, float(times[1] - times[0]) if len(times) > 1 else BUCKET_MS / 1000.0)
    win = max(1, int(round(baseline_win_s / step)))
    gap = max(1, int(round(min_gap_s / step)))
    # Nedensel taban: sadece geçmiş pencerenin medyanı (ani çıkışlar yakalanır).
    base = np.empty_like(curve)
    for i in range(len(curve)):
        lo = max(0, i - win)
        base[i] = np.median(curve[lo:i]) if i > lo else curve[i]
    hot = (curve - base >= delta_db) & (curve > floor_db)
    # Bitişik sıcak bucket'ları grupla, her grubun tepesini al.
    groups: List[List[int]] = []
    for i, flag in enumerate(hot):
        if flag and groups and i - groups[-1][-1] <= 1:
            groups[-1].append(i)
        elif flag:
            groups.append([i])
    candidates = []
    for g in groups:
        peak_idx = max(g, key=lambda i: curve[i])
        candidates.append({
            "index": peak_idx,
            "time": float(times[peak_idx]),
            "peak_db": round(float(curve[peak_idx]), 2),
            "delta_db": round(float(curve[peak_idx] - base[peak_idx]), 2),
        })
    # Minimum aralık: yakın adaylarda yüksek delta kazanır.
    candidates.sort(key=lambda c: -c["delta_db"])
    kept: List[Dict] = []
    for c in candidates:
        if all(abs(c["index"] - k["index"]) >= gap for k in kept):
            kept.append(c)
    kept.sort(key=lambda c: c["time"])
    return [
        {"time": c["time"], "peak_db": c["peak_db"], "delta_db": c["delta_db"]}
        for c in kept
    ]


def _overlap(a_start: float, a_end: float, intervals: List) -> bool:
    for iv in intervals:
        s = iv[0] if isinstance(iv, (list, tuple)) else iv.get("start", iv.get("s"))
        e = iv[1] if isinstance(iv, (list, tuple)) else iv.get("end", iv.get("e"))
        if float(s) < a_end and float(e) > a_start:
            return True
    return False


def score_highlight(
    spike: Dict, length: float,
    has_speech: bool = False, has_music: bool = False,
) -> Tuple[int, List[str]]:
    """Heuristik puan (0-100) + gerekçeler. Müzik üstü patlama kırpılır."""
    delta = float(spike.get("delta_db", 0.0))
    peak = float(spike.get("peak_db", -80.0))
    score = 40
    reasons: List[str] = []
    if delta >= 20:
        score += 30
        reasons.append(f"spike+{delta:.0f}db")
    elif delta >= 15:
        score += 20
        reasons.append(f"spike+{delta:.0f}db")
    else:
        score += 10
        reasons.append(f"spike+{delta:.0f}db")
    if peak >= -6:
        score += 10
        reasons.append("loud-peak")
    elif peak >= -12:
        score += 5
    if has_speech:
        score += 10
        reasons.append("has-speech")
    if has_music:
        score -= 15
        reasons.append("over-music")
    if length >= 6:
        score -= 5
        reasons.append("long-burst")
    return max(0, min(100, score)), reasons


def build_highlights(
    spikes: List[Dict],
    duration: float,
    pre_pad: float = 2.0,
    post_pad: float = 1.0,
    merge_gap: float = 1.0,
    speech: Optional[List] = None,
    music: Optional[List] = None,
) -> List[Dict]:
    """Spike -> highlight adayı: öncesine gerilim payı, çakışanlar birleşir."""
    speech = speech or []
    music = music or []
    raw = []
    for sp in spikes:
        s = max(0.0, float(sp["time"]) - pre_pad)
        e = min(float(duration), float(sp["time"]) + post_pad)
        if e - s <= 0:
            continue
        raw.append((s, e, sp))
    raw.sort(key=lambda r: r[0])
    merged: List[List] = []
    for s, e, sp in raw:
        if merged and s - merged[-1][1] <= merge_gap:
            prev = merged[-1]
            prev[1] = max(prev[1], e)
            if sp["delta_db"] > prev[2]["delta_db"]:
                prev[2] = sp
        else:
            merged.append([s, e, sp])
    out = []
    for s, e, sp in merged:
        has_speech = _overlap(s, e, speech)
        has_music = _overlap(s, e, music)
        score, reasons = score_highlight(sp, e - s, has_speech, has_music)
        out.append({
            "start": round(s, 3),
            "end": round(e, 3),
            "peak_db": sp["peak_db"],
            "delta_db": sp["delta_db"],
            "score": score,
            "reasons": reasons,
        })
    out.sort(key=lambda h: (-h["score"], h["start"]))
    return out


def analyze_events(
    path: Path,
    audio_track: int,
    duration: float,
    speech: Optional[List] = None,
    music: Optional[List] = None,
) -> List[Dict]:
    """Tek çağrı: eğri + spike + highlight + puan. Hata fırlatabilir."""
    times, curve = loudness_curve(path, audio_track)
    spikes = detect_spikes(times, curve)
    return build_highlights(spikes, duration, speech=speech, music=music)
