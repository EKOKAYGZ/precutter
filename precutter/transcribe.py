"""Speech transcription with faster-whisper + Silero VAD + music/filler layers.

Pipeline:
  video -> ffmpeg (16 kHz mono wav) -> Silero VAD (speech regions, RMS'ten
  daha dogru) -> faster-whisper (kelime zaman damgalari, dil otomatik
  tespit) -> muzik katmani (arka plan muzigini konusma sanmamak icin) ->
  dolgu kelime tespiti (tr/en) + filler_ratio.

Agir bagimliliklar (faster-whisper, torch) tembel yuklenir; yuklu
degillerse anlasilir bir MediaError yukselir. Saf yardimcilar
(normalize, filler, aralik aritmetigi, tonal müzik sezgiseli) modelsiz
test edilebilir.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import config
from .media import MediaError

Interval = Tuple[float, float]

SAMPLE_RATE = 16_000

# --- Dolgu kelimeleri -------------------------------------------------------
FILLER_WORDS_TR = {
    "ee", "e", "ıı", "ı", "mmm", "hmm",
    "şey", "yani", "işte", "hani", "falan", "filan",
    "neyse", "acaba", "herhalde", "galiba", "sanırım",
    "ya", "he", "ha",
}
# Normalize asagida yapildigi icin kisa formlari da tutuyoruz.
FILLER_SINGLE_TR = {"ee", "e", "ıı", "ı", "mmm", "hmm", "ya", "he", "ha"}

FILLER_WORDS_EN = {
    "um", "uh", "erm", "er", "ah", "hmm", "mmm",
    "like", "basically", "actually", "literally", "well",
}
FILLER_SINGLE_EN = {"um", "uh", "erm", "er", "ah", "hmm", "mmm", "like", "well"}

_WORD_CLEAN_RE = re.compile(r"[^\w']+", re.UNICODE)


def normalize_word(text: str) -> str:
    """Noktalama/kucuk harf normalizasyonu (tr/en)."""
    return _WORD_CLEAN_RE.sub("", text.lower()).strip("'")


def filler_set(language: Optional[str]) -> set:
    lang = (language or "auto").lower()
    if lang.startswith("tr"):
        return FILLER_WORDS_TR | FILLER_SINGLE_TR
    if lang.startswith("en"):
        return FILLER_WORDS_EN | FILLER_SINGLE_EN
    return FILLER_WORDS_TR | FILLER_WORDS_EN


# --- Veri tipleri ------------------------------------------------------------
@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0
    filler: bool = False


@dataclass
class Transcript:
    language: str
    words: List[Word] = field(default_factory=list)
    speech: List[Interval] = field(default_factory=list)
    music: List[Interval] = field(default_factory=list)
    silence: List[Interval] = field(default_factory=list)
    fillers: List[Word] = field(default_factory=list)
    filler_ratio: float = 0.0
    duration: float = 0.0
    cache_hit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# --- Onbellek (.precutter/, hash ile) ----------------------------------------
def cache_dir() -> Path:
    d = Path(config.PROJECT_ROOT) / ".precutter"
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_fingerprint(path: Path) -> str:
    """Dosya hash'i (ilk/orta/son bloklar + boyut) — hizli ve yeterli."""
    h = hashlib.sha256()
    size = path.stat().st_size
    h.update(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(1 << 20))
        if size > 3 << 20:
            f.seek(size // 2)
            h.update(f.read(1 << 20))
            f.seek(max(0, size - (1 << 20)))
            h.update(f.read(1 << 20))
    return h.hexdigest()[:32]


def cache_key(fingerprint: str, model: str, language: Optional[str], audio_track: int = 0) -> str:
    lang = (language or "auto").lower()
    return f"{fingerprint}_{model}_{lang}_t{audio_track}.json"


def load_cache(path: Path, model: str, language: Optional[str], audio_track: int = 0) -> Optional[Dict[str, Any]]:
    key = cache_key(file_fingerprint(path), model, language, audio_track)
    cache_file = cache_dir() / key
    if not cache_file.exists():
        return None
    try:
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_cache(path: Path, model: str, language: Optional[str], payload: Dict[str, Any], audio_track: int = 0) -> None:
    key = cache_key(file_fingerprint(path), model, language, audio_track)
    try:
        (cache_dir() / key).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # onbellek yazilamazsa sessizce gec


# --- Ses cikarma -------------------------------------------------------------
def extract_wav(source: Path, sr: int = SAMPLE_RATE, audio_track: int = 0) -> Path:
    """Videodan 16 kHz mono wav cikarir (gecici dosya)."""
    if not source.exists():
        raise MediaError(f"File not found: {source}")
    tmp = Path(tempfile.mkstemp(suffix=".wav")[1])
    cmd = [
        config.FFMPEG_BIN, "-hide_banner", "-y", "-i", str(source),
        "-map", f"0:a:{audio_track}",
        "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(tmp),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise MediaError("ffmpeg not found. Install ffmpeg and add it to PATH.") from exc
    if result.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        raise MediaError(f"Audio extract failed: {(result.stderr or '')[-500:] or 'unknown error'}")
    return tmp


def read_wav_mono(path: Path, sr: int = SAMPLE_RATE) -> "list[float]":
    """Saf stdlib wav okuma -> float ornekler. numpy yoksa liste doner."""
    import numpy as np  # hizli yol

    with wave.open(str(path), "rb") as w:
        n = w.getnframes()
        raw = w.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
        if w.getframerate() != sr:
            # Kaba yeniden ornekleme (ffmpeg zaten 16k uretir; guvenlik agi).
            idx = (np.arange(int(n * sr / w.getframerate())) * w.getframerate() / sr).astype(int)
            idx = np.clip(idx, 0, len(data) - 1)
            data = data[idx]
        return data


# --- Aralik aritmetigi (saf, test edilebilir) --------------------------------
def merge_intervals(intervals: List[Interval], max_gap: float = 0.0) -> List[Interval]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0]]
    for s, e in ordered[1:]:
        ls, le = merged[-1]
        if s <= le + max_gap:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return [(round(s, 3), round(e, 3)) for s, e in merged]


def subtract_intervals(base: List[Interval], cut: List[Interval]) -> List[Interval]:
    """base'ten cut araliklarini cikarir."""
    result: List[Interval] = []
    for bs, be in sorted(base):
        cursor = bs
        for cs, ce in sorted(cut):
            if ce <= cursor or cs >= be:
                continue
            if cs > cursor:
                result.append((cursor, min(cs, be)))
            cursor = max(cursor, ce)
            if cursor >= be:
                break
        if cursor < be:
            result.append((cursor, be))
    return [(round(s, 3), round(e, 3)) for s, e in result if e - s > 1e-6]


def words_to_speech(words: List[Word], max_gap: float = 0.4, pad: float = 0.1,
                    duration: Optional[float] = None) -> List[Interval]:
    spans = [(w.start - pad, w.end + pad) for w in words]
    merged = merge_intervals(spans, max_gap=max_gap)
    if duration is not None:
        merged = [(max(0.0, s), min(duration, e)) for s, e in merged if e > 0 and s < duration]
    return [(round(s, 3), round(e, 3)) for s, e in merged if e - s > 1e-6]


def silence_from_speech(speech: List[Interval], duration: float) -> List[Interval]:
    gaps: List[Interval] = []
    cursor = 0.0
    for s, e in sorted(speech):
        if s > cursor:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        gaps.append((cursor, duration))
    return [(round(s, 3), round(e, 3)) for s, e in gaps]


# --- Silero VAD --------------------------------------------------------------
_silero_cache: Dict[str, Any] = {}


def _load_silero() -> Tuple[Any, Any]:
    """Silero VAD model + utils. torch yoksa MediaError."""
    try:
        import torch
    except ImportError as exc:
        raise MediaError("torch is required for Silero VAD. Run: pip install torch torchaudio") from exc
    if "model" in _silero_cache:
        return _silero_cache["model"], _silero_cache["utils"]
    try:
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad", force_reload=False, trust_repo=True,
        )
    except Exception as exc:
        raise MediaError(f"Could not load Silero VAD model: {exc}") from exc
    _silero_cache["model"] = model
    _silero_cache["utils"] = utils
    return model, utils


def silero_speech(wav_path: Path, threshold: float = 0.5,
                  min_speech_ms: int = 250, min_silence_ms: int = 300) -> List[Interval]:
    """Silero VAD ile konusma araliklari. Model yuklenemezse enerji-VAD'e duser."""
    try:
        model, utils = _load_silero()
    except MediaError:
        return energy_speech_fallback(wav_path)
    get_timestamps = utils[0]
    try:
        import torch
        wav = read_wav_mono(wav_path)
        import numpy as _np
        tensor = torch.from_numpy(_np.asarray(wav, dtype=_np.float32))
        stamps = get_timestamps(
            tensor, model, threshold=threshold,
            min_speech_duration_ms=min_speech_ms, min_silence_duration_ms=min_silence_ms,
            sampling_rate=SAMPLE_RATE,
        )
        return [(round(s["start"] / SAMPLE_RATE, 3), round(s["end"] / SAMPLE_RATE, 3)) for s in stamps]
    except Exception:
        return energy_speech_fallback(wav_path)


def energy_speech_fallback(wav_path: Path, frame_s: float = 0.03,
                            threshold_ratio: float = 0.15) -> List[Interval]:
    """Model yokken calisan basit enerji VAD'i (RMS esigi)."""
    import numpy as np

    data = np.asarray(read_wav_mono(wav_path), dtype=np.float32)
    n = int(frame_s * SAMPLE_RATE)
    if n <= 0 or len(data) == 0:
        return []
    frames = data[: len(data) - len(data) % n].reshape(-1, n)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    thr = float(rms.max()) * threshold_ratio
    active = rms > thr
    intervals: List[Interval] = []
    start = None
    for i, on in enumerate(active):
        if on and start is None:
            start = i * frame_s
        elif not on and start is not None:
            intervals.append((start, i * frame_s))
            start = None
    if start is not None:
        intervals.append((start, len(active) * frame_s))
    return merge_intervals(intervals, max_gap=0.2)


# --- Muzik katmani -----------------------------------------------------------
def tonal_music_mask(samples: "list[float]", sr: int = SAMPLE_RATE,
                      frame_s: float = 0.5, hop_s: float = 0.25,
                      min_len: float = 2.0) -> List[Interval]:
    """Saf sinyal sezgiseli: dusuk spektral flux + surekli enerji = muzik.

    Konusma spektrumu hizli degisir (yuksek flux); arka plan muzigi daha
    kararli ve sureklidir. numpy ile modelsiz calisir.
    """
    import numpy as np

    x = np.asarray(samples, dtype=np.float32)
    if len(x) < sr:
        return []
    fl, hl = int(frame_s * sr), int(hop_s * sr)
    window = np.hanning(fl)
    prev_mag = None
    fluxes, energies = [], []
    for start in range(0, len(x) - fl + 1, hl):
        frame = x[start:start + fl] * window
        mag = np.abs(np.fft.rfft(frame))
        energies.append(float((frame ** 2).mean()))
        if prev_mag is not None:
            denom = float((prev_mag ** 2).sum() + 1e-9)
            fluxes.append(float(((mag - prev_mag) ** 2).sum() / denom))
        prev_mag = mag
    if not fluxes:
        return []
    energies = np.asarray(energies[1:])
    fluxes = np.asarray(fluxes)
    e_med = float(np.median(energies)) + 1e-9
    # Bıçak-sırtı persentil kararlarini onlemek icin mutlak taban:
    # neredeyse sifir flux = kararli ton (saf sinuste ~1e-28 mertebesi).
    flux_thr = max(float(np.percentile(fluxes, 60)), 1e-9)
    # Muzik adayi: enerjisi medyanin uzerinde VE degisimi dusuk.
    music_frames = (energies > 0.8 * e_med) & (fluxes <= flux_thr)
    # Cerceve bazinda kararlar kirpilir; kisa bosluklari tolere edip birlestir.
    micro = [(i * hop_s, i * hop_s + hop_s) for i, on in enumerate(music_frames) if on]
    return [iv for iv in merge_intervals(micro, max_gap=0.5) if iv[1] - iv[0] >= min_len]


def whisper_music_candidates(segments: List[Dict[str, Any]],
                              no_speech_thr: float = 0.6,
                              min_len: float = 1.0) -> List[Interval]:
    """Whisper'in no_speech_prob yuksek segmentleri = muzik/ses efekti adayi."""
    out: List[Interval] = []
    for seg in segments:
        try:
            p = float(seg.get("no_speech_prob", 0.0))
        except (TypeError, ValueError):
            p = 0.0
        s, e = float(seg.get("start", 0.0)), float(seg.get("end", 0.0))
        if p >= no_speech_thr and e - s >= min_len:
            out.append((s, e))
    return merge_intervals(out)


def build_music_layer(wav_samples: "list[float]",
                      whisper_segments: List[Dict[str, Any]],
                      confirmed_speech: List[Interval]) -> List[Interval]:
    """Tonal + whisper adaylarini birlestirip kesin konusmayi cikarir."""
    tonal = tonal_music_mask(wav_samples)
    whisper_cand = whisper_music_candidates(whisper_segments)
    # Kesisim agirlikli: iki kaynagin da muzik dedigi guclu, birinin dedigi zayif.
    strong = []
    for a in tonal:
        for b in whisper_cand:
            lo, hi = max(a[0], b[0]), min(a[1], b[1])
            if hi - lo >= 0.5:
                strong.append((lo, hi))
    candidates = merge_intervals(strong + whisper_cand + tonal)
    # Kesin konusma (yuksek prob'lu kelimeler) muzikten cikarilir.
    return subtract_intervals(candidates, confirmed_speech)


# Whisper inference runs in chunks so progress can be reported on long
# files (and a single huge array never has to sit in memory twice).
TRANSCRIBE_CHUNK_SECONDS = 60.0
TRANSCRIBE_CHUNK_OVERLAP = 2.0


def _chunk_windows(total_samples: int, sample_rate: int,
                   chunk_seconds: float = TRANSCRIBE_CHUNK_SECONDS,
                   overlap_seconds: float = TRANSCRIBE_CHUNK_OVERLAP):
    """Yield (chunk_start_sec, samples) windows with a small overlap.

    The overlap avoids cutting words at boundaries; the caller drops
    words/segments that fall inside the overlapped head of chunks after
    the first one.
    """
    chunk_len = int(chunk_seconds * sample_rate)
    overlap_len = int(overlap_seconds * sample_rate)
    start = 0
    while start < total_samples:
        end = min(start + chunk_len + (overlap_len if start + chunk_len < total_samples else 0),
                  total_samples)
        yield start / sample_rate, slice(start, end)
        start += chunk_len
        if start >= total_samples:
            break


# --- faster-whisper ----------------------------------------------------------
_whisper_cache: Dict[str, Any] = {}


def whisper_device() -> str:
    """faster-whisper'ın inference motoru için cihaz seç.

    Asıl motor CTranslate2'dir; torch'a bakmak sadece yedek. ct2 CPU ile
    derlendiyse torch CUDA görse bile GPU kullanılamaz — bu yüzden öncelik
    ct2'nin kendi CUDA sayaçlıdır.
    """
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def gpu_name() -> Optional[str]:
    """GPU adı (yoksa None). Ayarlar'daki Sistem durumu için."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


def _load_whisper(model_size: str = "base"):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise MediaError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from exc
    if model_size in _whisper_cache:
        return _whisper_cache[model_size]
    device = whisper_device()
    try:
        model = WhisperModel(model_size, device=device,
                             compute_type="float16" if device == "cuda" else "int8")
    except Exception as exc:
        raise MediaError(f"Could not load whisper model '{model_size}': {exc}") from exc
    _whisper_cache[model_size] = model
    return model


# --- Ana API -----------------------------------------------------------------
def transcribe_file(
    source: Path,
    model_size: Optional[str] = None,
    language: Optional[str] = None,
    use_cache: bool = True,
    use_silero: bool = True,
    detect_music: bool = True,
    audio_track: int = 0,
    progress=None,
) -> Transcript:
    """Videoyu transcribe et; VAD + whisper + muzik + dolgu katmanlariyla.

    language=None -> otomatik tespit. audio_track secili ses izini kullanir.
    progress, if given, is called as progress(done_chunks, total_chunks)
    after each Whisper chunk (None on cache hit).
    """
    model_size = model_size or getattr(config, "WHISPER_MODEL", "base")
    if not source.exists():
        raise MediaError(f"File not found: {source}")

    if use_cache:
        cached = load_cache(source, model_size, language, audio_track)
        if cached is not None:
            return _transcript_from_dict(cached, cache_hit=True)

    from .media import get_duration
    duration = get_duration(source)
    wav_path = extract_wav(source, audio_track=audio_track)
    try:
        if use_silero:
            vad_speech = silero_speech(wav_path)
        else:
            vad_speech = energy_speech_fallback(wav_path)

        model = _load_whisper(model_size)
        # Nota: dosya yolu yerine numpy dizisi veriyoruz. faster-whisper
        # dosya yolunda PyAV ile çözer (av>=14 ile bozulan metadata_errors
        # argümanı yüzünden); diziyle bu katman tamamen atlanır. wav zaten
        # 16 kHz mono olduğundan örnekleme de birebir uyar.
        import numpy as _np

        wav_samples = _np.asarray(read_wav_mono(wav_path), dtype=_np.float32)
        windows = list(_chunk_windows(len(wav_samples), SAMPLE_RATE))
        total_chunks = len(windows)
        raw_seg_dicts = []
        detected_langs = []
        words: List[Word] = []
        try:
            for chunk_index, (chunk_start, sl) in enumerate(windows):
                chunk = wav_samples[sl]
                whisper_segments, info = model.transcribe(
                    chunk, language=language, word_timestamps=True,
                    vad_filter=False, beam_size=5,
                )
                chunk_lang = getattr(info, "language", None)
                if chunk_lang:
                    detected_langs.append(chunk_lang)
                is_first = chunk_index == 0
                for seg in whisper_segments:
                    seg_start = float(seg.start) + chunk_start
                    seg_end = float(seg.end) + chunk_start
                    if not is_first and seg_start < chunk_start + TRANSCRIBE_CHUNK_OVERLAP:
                        continue  # overlapped head: previous chunk has the full version
                    raw_seg_dicts.append({
                        "start": seg_start, "end": seg_end,
                        "no_speech_prob": float(getattr(seg, "no_speech_prob", 0.0)),
                        "avg_logprob": float(getattr(seg, "avg_logprob", 0.0)),
                        "_seg": seg, "_offset": chunk_start,
                        "_first": is_first,
                    })
                if progress is not None:
                    progress(chunk_index + 1, total_chunks)
        except Exception as exc:
            raise MediaError(f"Transcription failed: {exc}") from exc
        if detected_langs:
            detected_lang = max(set(detected_langs), key=detected_langs.count)
        else:
            detected_lang = language or "auto"

        fset = filler_set(detected_lang)
        for entry in raw_seg_dicts:
            seg = entry["_seg"]
            chunk_start = entry["_offset"]
            for w in (getattr(seg, "words", None) or []):
                w_start = float(w.start) + chunk_start
                if not entry["_first"] and w_start < chunk_start + TRANSCRIBE_CHUNK_OVERLAP:
                    continue
                norm = normalize_word(w.word)
                is_filler = norm in fset
                words.append(Word(text=w.word.strip(), start=w_start,
                                  end=float(w.end) + chunk_start,
                                  prob=float(getattr(w, "probability", 1.0)),
                                  filler=is_filler))
        for entry in raw_seg_dicts:
            del entry["_seg"]
            del entry["_offset"]
            del entry["_first"]
        fillers = [w for w in words if w.filler]
        filler_ratio = round(len(fillers) / max(1, len(words)), 4)

        word_speech = words_to_speech(words, duration=duration)
        # VAD + kelime kesisimi = guvenilir konusma.
        speech = merge_intervals(vad_speech + word_speech, max_gap=0.3)
        confirmed = [ (w.start, w.end) for w in words if w.prob >= 0.5 ]

        music: List[Interval] = []
        if detect_music:
            music = build_music_layer(wav_samples, raw_seg_dicts, confirmed_speech=confirmed)
            speech = subtract_intervals(speech, music)

        silence = silence_from_speech(merge_intervals(speech), duration)
        tr = Transcript(language=detected_lang, words=words, speech=speech,
                        music=music, silence=silence, fillers=fillers,
                        filler_ratio=filler_ratio, duration=round(duration, 3))
        if use_cache:
            save_cache(source, model_size, language, tr.to_dict(), audio_track)
        return tr
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except OSError:
            pass


def _transcript_from_dict(data: Dict[str, Any], cache_hit: bool = False) -> Transcript:
    words = [Word(**w) for w in data.get("words", [])]
    fillers = [Word(**w) for w in data.get("fillers", [])]
    return Transcript(
        language=data.get("language", "auto"), words=words,
        speech=[tuple(x) for x in data.get("speech", [])],
        music=[tuple(x) for x in data.get("music", [])],
        silence=[tuple(x) for x in data.get("silence", [])],
        fillers=fillers, filler_ratio=float(data.get("filler_ratio", 0.0)),
        duration=float(data.get("duration", 0.0)), cache_hit=cache_hit,
    )


def filler_intervals(words: List[Word], pad: float = 0.05) -> List[Interval]:
    """Kesilmek uzere dolgu kelime araliklari."""
    return merge_intervals([(max(0.0, w.start - pad), w.end + pad) for w in words if w.filler])


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(words: List[Word], keep: List[Interval]) -> str:
    """Transcript words remapped onto the cut timeline, as SRT text.

    Words inside cut regions are dropped; kept words shift left by the total
    cut time before them. Cues break on gaps > 0.8 s or runs > 14 words.
    """
    kept = sorted(keep)
    cues: List[List[Word]] = []
    current: List[Word] = []
    current_end = 0.0

    def _new_time(t: float) -> Optional[float]:
        elapsed = 0.0
        for ks, ke in kept:
            if t < ks:
                return None
            if t <= ke:
                return elapsed + (t - ks)
            elapsed += ke - ks
        return None

    for word in sorted(words, key=lambda w: w.start):
        start = _new_time(word.start)
        end = _new_time(word.end)
        if start is None:
            continue
        if end is None:
            end = start + max(word.end - word.start, 0.04)
        if current and (start - current_end > 0.8 or len(current) >= 14):
            cues.append(current)
            current = []
        current.append(Word(word.text, start, end, word.prob, word.filler))
        current_end = end
    if current:
        cues.append(current)
    blocks = []
    for index, cue in enumerate(cues, start=1):
        text = " ".join(w.text for w in cue)
        blocks.append(
            f"{index}\n{_srt_timestamp(cue[0].start)} --> "
            f"{_srt_timestamp(cue[-1].end)}\n{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")
