"""Configuration settings for PreCutter."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
UPLOADS_DIR = WORKSPACE_DIR / "uploads"
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"

THRESHOLD_DB = -35
MIN_SILENCE = 0.6
PADDING = 0.15

ALLOWED_EXTENSIONS = {".mp4", ".mkv", ".mov"}

# Upload / video sinirlari.
MAX_UPLOAD_BYTES = 4 * 1024**3  # 4 GiB
MAX_VIDEO_DURATION = 4 * 3600.0  # 4 saat (sn)

MAX_SEGMENTS_PER_BATCH = 100
MIN_SEGMENT_DURATION = 0.1

FFMPEG_BIN = "ffmpeg"
FFPROBE_BIN = "ffprobe"

WHISPER_MODEL = "base"


def ensure_dirs() -> None:
    """Create workspace directories if they don't exist."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)