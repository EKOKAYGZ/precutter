"""Configuration settings for PreCutter."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
UPLOADS_DIR = WORKSPACE_DIR / "uploads"
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"

THRESHOLD_DB = -35
MIN_SILENCE = 0.6
PADDING_PRE = 0.2
PADDING_POST = 0.25
MIN_KEEP = 0.3
MERGE_GAP = 0.3

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".mov"}

# Upload / video sinirlari.
MAX_UPLOAD_BYTES = 4 * 1024**3  # 4 GiB
MAX_VIDEO_DURATION = 4 * 3600.0  # 4 saat (sn)

MIN_SEGMENT_DURATION = 0.1

FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

WHISPER_MODEL = "base"

# v0.4 AI (Ollama, local): tek model hem vision hem puanlama.
# GPU varsa Ollama kullanır, yoksa CPU.
OLLAMA_HOST = "http://127.0.0.1:11434"
AI_MODEL = "qwen3-vl:4b"
AI_VISION_MODELS = ("qwen3-vl:4b", "gemma3:4b")
AI_THRESHOLD = 30

# Kodlayıcı tercihi: "auto" (NVENC varsa onu kullan), "nvenc", "x264".
ENCODER_PREF = "auto"

# Çıktı sesi: "mix" (mikrofon+oyun karışımı 1. iz + orijinaller),
# "separate" (izler ayrı, mikrofon varsayılan), "miconly" (sadece mikrofon).
OUTPUT_AUDIO = "mix"

# Kalite: "match" (kaynak bit hızına uyar), "high", "small".
QUALITY = "match"


def ensure_dirs() -> None:
    """Create workspace directories if they don't exist."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)