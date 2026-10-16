"""Kullanıcı ayarları: workspace/settings.json içinde saklanır, config'i geçersiz kılar.

Varsayılanlar config.py'da durur (repoya girer); kullanıcının değişiklikleri
workspace'e yazılır (git'e girmez). PUT /settings ile güncellenir ve yeniden
başlatma gerekmeden uygulanır.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from . import config

SETTINGS_FILE = config.WORKSPACE_DIR / "settings.json"

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo"]
ENCODERS = ["auto", "nvenc", "x264"]
QUALITIES = ["match", "high", "small"]
OUTPUT_AUDIOS = ["mix", "separate", "miconly"]
PRESETS = ["game", "interview", "chat"]

DEFAULTS: Dict[str, Any] = {
    "threshold_db": config.THRESHOLD_DB,
    "min_silence": config.MIN_SILENCE,
    "padding_pre": config.PADDING_PRE,
    "padding_post": config.PADDING_POST,
    "whisper_model": config.WHISPER_MODEL,
    "encoder": "auto",
    "quality": config.QUALITY,
    "output_audio": config.OUTPUT_AUDIO,
    "preset": "game",
    "max_upload_gb": round(config.MAX_UPLOAD_BYTES / 1024**3),
    "ollama_host": config.OLLAMA_HOST,
    "ai_model": config.AI_MODEL,
    "ai_threshold": config.AI_THRESHOLD,
}


def _validate(patch: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    if "threshold_db" in patch:
        v = float(patch["threshold_db"])
        if not -60 <= v <= -10:
            raise ValueError("threshold_db must be between -60 and -10.")
        clean["threshold_db"] = v
    if "min_silence" in patch:
        v = float(patch["min_silence"])
        if not 0.2 <= v <= 3.0:
            raise ValueError("min_silence must be between 0.2 and 3.0.")
        clean["min_silence"] = v
    if "padding_pre" in patch:
        v = float(patch["padding_pre"])
        if not 0.0 <= v <= 1.0:
            raise ValueError("padding_pre must be between 0.0 and 1.0.")
        clean["padding_pre"] = v
    if "padding_post" in patch:
        v = float(patch["padding_post"])
        if not 0.0 <= v <= 1.0:
            raise ValueError("padding_post must be between 0.0 and 1.0.")
        clean["padding_post"] = v
    if "whisper_model" in patch:
        v = str(patch["whisper_model"])
        if v not in WHISPER_MODELS:
            raise ValueError(f"whisper_model must be one of {WHISPER_MODELS}.")
        clean["whisper_model"] = v
    if "encoder" in patch:
        v = str(patch["encoder"])
        if v not in ENCODERS:
            raise ValueError(f"encoder must be one of {ENCODERS}.")
        clean["encoder"] = v
    if "quality" in patch:
        v = str(patch["quality"])
        if v not in QUALITIES:
            raise ValueError(f"quality must be one of {QUALITIES}.")
        clean["quality"] = v
    if "output_audio" in patch:
        v = str(patch["output_audio"])
        if v not in OUTPUT_AUDIOS:
            raise ValueError(f"output_audio must be one of {OUTPUT_AUDIOS}.")
        clean["output_audio"] = v
    if "preset" in patch:
        v = str(patch["preset"])
        if v not in PRESETS:
            raise ValueError(f"preset must be one of {PRESETS}.")
        clean["preset"] = v
    if "max_upload_gb" in patch:
        v = float(patch["max_upload_gb"])
        if not 1 <= v <= 20:
            raise ValueError("max_upload_gb must be between 1 and 20.")
        clean["max_upload_gb"] = v
    if "ollama_host" in patch:
        v = str(patch["ollama_host"]).strip().rstrip("/")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("ollama_host must be an http(s) URL.")
        clean["ollama_host"] = v
    if "ai_model" in patch:
        v = str(patch["ai_model"]).strip()
        if not v or len(v) > 80:
            raise ValueError("ai_model must be a non-empty Ollama tag.")
        clean["ai_model"] = v
    if "ai_threshold" in patch:
        v = int(patch["ai_threshold"])
        if not 10 <= v <= 70:
            raise ValueError("ai_threshold must be between 10 and 70.")
        clean["ai_threshold"] = v
    unknown = set(patch) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown settings: {sorted(unknown)}.")
    return clean


def load() -> Dict[str, Any]:
    """Kayıtlı ayarları varsayılanlarla birleştirip döndürür."""
    merged = dict(DEFAULTS)
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if isinstance(stored, dict):
        for key in DEFAULTS:
            if key in stored:
                merged[key] = stored[key]
    return merged


def apply_to_config(values: Dict[str, Any]) -> None:
    """Ayarları canlı config modülüne uygular (yeniden başlatma gerekmez)."""
    config.THRESHOLD_DB = float(values["threshold_db"])
    config.MIN_SILENCE = float(values["min_silence"])
    config.PADDING_PRE = float(values["padding_pre"])
    config.PADDING_POST = float(values["padding_post"])
    config.WHISPER_MODEL = str(values["whisper_model"])
    config.ENCODER_PREF = str(values["encoder"])
    config.QUALITY = str(values["quality"])
    config.OUTPUT_AUDIO = str(values["output_audio"])
    config.MAX_UPLOAD_BYTES = int(float(values["max_upload_gb"]) * 1024**3)
    config.OLLAMA_HOST = str(values["ollama_host"])
    config.AI_MODEL = str(values["ai_model"])
    config.AI_THRESHOLD = int(values["ai_threshold"])
    # Kodlayıcı önbelleğini boz (tercih değişmiş olabilir).
    from . import media

    media._ENCODER_CACHE.clear()


def save(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Parçalı güncellemeyi doğrula, kaydet, uygula; güncel ayarları döndür."""
    clean = _validate(patch)
    current = load()
    current.update(clean)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    apply_to_config(current)
    return current


def init() -> Dict[str, Any]:
    """Sunucu açılışında kayıtlı ayarları uygular."""
    values = load()
    apply_to_config(values)
    return values
