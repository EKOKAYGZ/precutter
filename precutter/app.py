"""FastAPI application for PreCutter."""
import shutil
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, media, render, segments, silence

app = FastAPI(title="PreCutter", version="0.1.0")
config.ensure_dirs()

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


class ProcessRequest(BaseModel):
    filename: str
    threshold_db: float = Field(default=config.THRESHOLD_DB, ge=-60, le=-10)
    min_silence: float = Field(default=config.MIN_SILENCE, ge=0.2, le=3.0)
    padding: float = Field(default=config.PADDING, ge=0.0, le=0.5)
    audio_track: int = Field(default=0, ge=0)
    audio_channel: Optional[int] = Field(default=None, ge=0, le=7)


class TranscribeRequest(BaseModel):
    filename: str
    model: str = Field(default=config.WHISPER_MODEL)
    language: Optional[str] = None
    remove_fillers: bool = False
    audio_track: int = Field(default=0, ge=0)


def _safe_upload_path(filename: str) -> Path:
    """Resolve an uploaded filename inside the uploads dir, blocking traversal."""
    name = Path(filename).name
    path = (config.UPLOADS_DIR / name).resolve()
    if config.UPLOADS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found.")
    return path


def _check_audio_selection(path: Path, audio_track: int, audio_channel: Optional[int]) -> None:
    """Validate the requested track/channel against the file's audio streams."""
    streams = media.audio_streams(path)
    if not streams:
        raise media.MediaError("File has no audio streams to analyze.")
    if audio_track >= len(streams):
        raise media.MediaError(
            f"Audio track {audio_track} not found. File has {len(streams)} audio track(s)."
        )
    if audio_channel is not None and audio_channel >= streams[audio_track]["channels"]:
        raise media.MediaError(
            f"Audio channel {audio_channel} not found. "
            f"Track {audio_track} has {streams[audio_track]['channels']} channel(s)."
        )


def _check_duration(duration: float) -> None:
    """Reject videos longer than MAX_VIDEO_DURATION."""
    if duration > config.MAX_VIDEO_DURATION:
        hours = config.MAX_VIDEO_DURATION / 3600
        raise media.MediaError(
            f"Video too long ({duration / 3600:.1f}h). Maximum is {hours:.0f}h."
        )


def _probe_duration_best_effort(path: Path) -> Optional[float]:
    """Return duration or None (e.g. ffprobe missing) — never raises."""
    try:
        return media.get_duration(path)
    except media.MediaError:
        return None


def _analyze_file(path: Path, req: ProcessRequest) -> tuple[float, List[list], dict]:
    duration = media.get_duration(path)
    _check_duration(duration)
    _check_audio_selection(path, req.audio_track, req.audio_channel)
    silences = silence.detect_silence(
        path, req.threshold_db, req.min_silence, duration,
        audio_track=req.audio_track, channel=req.audio_channel,
    )
    keep = segments.build_segments(silences, duration, req.padding)
    summary = segments.summarize(duration, keep)
    summary["estimated_render_seconds"] = _estimate_render_seconds(summary)
    return duration, [[round(s, 3), round(e, 3)] for s, e in keep], summary


def _estimate_render_seconds(summary: dict) -> float:
    """Heuristic render-time estimate: re-encode cost scales with kept duration."""
    new_duration = float(summary.get("new_duration", 0.0))
    segment_count = int(summary.get("segment_count", 0))
    estimate = 2.0 + new_duration * 0.4 + segment_count * 0.15
    return round(estimate, 1)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(Path(__file__).parent / "static" / "index.html"))


@app.get("/health")
def health() -> dict:
    from . import transcribe as transcribe_mod

    return {
        "status": "ok",
        "ffmpeg": shutil.which(config.FFMPEG_BIN) is not None,
        "ffprobe": shutil.which(config.FFPROBE_BIN) is not None,
        "encoder": media.encoder_name() if shutil.which(config.FFMPEG_BIN) else None,
        "limits": {
            "max_upload_bytes": config.MAX_UPLOAD_BYTES,
            "max_video_duration": config.MAX_VIDEO_DURATION,
            "allowed_extensions": sorted(config.ALLOWED_EXTENSIONS),
        },
        "transcribe_models_cached": sorted(
            p.stem for p in transcribe_mod.cache_dir().glob("*.json")
        ) if transcribe_mod.cache_dir().exists() else [],
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    original = file.filename or ""
    suffix = Path(original).suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}.",
        )
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = config.UPLOADS_DIR / stored_name
    size_bytes = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size_bytes += len(chunk)
                if size_bytes > config.MAX_UPLOAD_BYTES:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum is {config.MAX_UPLOAD_BYTES / 1024**3:.0f} GB.",
                    )
                handle.write(chunk)
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not save upload: {exc}") from exc
    finally:
        await file.close()
    duration = _probe_duration_best_effort(destination)
    if duration is not None and duration > config.MAX_VIDEO_DURATION:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=f"Video too long. Maximum is {config.MAX_VIDEO_DURATION / 3600:.0f}h.",
        )
    try:
        streams = media.audio_streams(destination, include_loudness=False)
    except media.MediaError:
        streams = []
    return {
        "filename": stored_name,
        "original_name": original,
        "size_bytes": size_bytes,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "audio_streams": streams,
    }


@app.post("/analyze")
def analyze(req: ProcessRequest) -> dict:
    path = _safe_upload_path(req.filename)
    try:
        duration, keep, summary = _analyze_file(path, req)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"duration": round(duration, 3), "segments": keep, "summary": summary}


@app.post("/render")
def render_video(req: ProcessRequest) -> dict:
    """Start a render in the background; poll GET /jobs/{job_id} for progress.

    Long renders (tens of minutes) would otherwise outlive the HTTP connection
    and surface as an opaque "Failed to fetch" in the browser.
    """
    path = _safe_upload_path(req.filename)
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "working", "stage": "analyze", "done": 0, "total": None}
    thread = threading.Thread(
        target=_run_render_job, args=(job_id, path, req.model_dump()), daemon=True
    )
    thread.start()
    return {"job_id": job_id}


def _run_render_job(job_id: str, path: Path, req_data: dict) -> None:
    try:
        req = ProcessRequest(**req_data)
        duration, keep, summary = _analyze_file(path, req)
        if not keep:
            raise media.MediaError("Nothing to keep after analysis.")
        output_name = f"{uuid.uuid4().hex}.mp4"
        output_path = config.OUTPUTS_DIR / output_name
        segments = [(s, e) for s, e in keep]

        def on_progress(done: int, total: int) -> None:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job.update(status="working", stage="render", done=done, total=total)

        with _jobs_lock:
            _jobs[job_id].update(stage="render", done=0, total=len(segments))
        render.render(path, segments, output_path, progress=on_progress)
        try:
            out_tracks = len(media.audio_streams(output_path, include_loudness=False))
        except media.MediaError:
            out_tracks = None
        with _jobs_lock:
            _jobs[job_id].update(
                status="done", done=len(segments), total=len(segments),
                filename=output_name, download_url=f"/download/{output_name}",
                summary=summary, output_audio_tracks=out_tracks,
            )
    except media.MediaError as exc:
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=str(exc))
    except Exception as exc:  # unexpected: keep the message, never hang the poll
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=f"Render failed: {exc}")


_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()


@app.get("/jobs/{job_id}")
def render_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job_id, **job}


@app.get("/preview-audio/{name}")
def preview_audio(name: str, track: int = 0) -> FileResponse:
    """Extract one audio track as a small preview file (cached) for auditioning.

    Lets users hear which track is the mic before analyzing.
    """
    path = _safe_upload_path(name)
    if track < 0:
        raise HTTPException(status_code=400, detail="Invalid track.")
    try:
        streams = media.audio_streams(path, include_loudness=False)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if track >= len(streams):
        raise HTTPException(
            status_code=400,
            detail=f"Audio track {track} not found. File has {len(streams)} track(s).",
        )
    previews = config.WORKSPACE_DIR / "previews"
    previews.mkdir(parents=True, exist_ok=True)
    cached = previews / f"{path.stem}_t{track}.m4a"
    if not cached.exists():
        import subprocess as _sp

        cmd = [
            config.FFMPEG_BIN, "-hide_banner", "-y",
            "-i", str(path),
            "-map", f"0:a:{track}",
            "-c:a", "aac", "-b:a", "128k",
            str(cached),
        ]
        try:
            result = _sp.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail="ffmpeg not found.") from exc
        if result.returncode != 0 or not cached.exists():
            raise HTTPException(status_code=400, detail="Could not extract audio preview.")
    return FileResponse(str(cached), media_type="audio/mp4")


@app.get("/projects")
def projects() -> dict:
    """List uploaded project files (newest first) with size and duration."""
    items = []
    for path in sorted(
        config.UPLOADS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        if not path.is_file() or path.suffix.lower() not in config.ALLOWED_EXTENSIONS:
            continue
        try:
            duration = media.get_duration(path)
        except media.MediaError:
            duration = None
        try:
            track_count = len(media.audio_streams(path, include_loudness=False))
        except media.MediaError:
            track_count = 0
        items.append(
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "duration_seconds": round(duration, 3) if duration is not None else None,
                "audio_tracks": track_count,
            }
        )
    return {"projects": items}


@app.post("/streams")
def streams(req: TranscribeRequest) -> dict:
    """List audio tracks/channels so the UI can offer a source selector."""
    path = _safe_upload_path(req.filename)
    try:
        duration = media.get_duration(path)
        tracks = media.audio_streams(path)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"duration": round(duration, 3), "audio_streams": tracks}


@app.post("/transcribe")
def transcribe(req: TranscribeRequest) -> dict:
    from . import transcribe as transcribe_mod

    path = _safe_upload_path(req.filename)
    try:
        duration = media.get_duration(path)
        _check_duration(duration)
        _check_audio_selection(path, req.audio_track, None)
        result = transcribe_mod.transcribe_file(
            path, model_size=req.model or config.WHISPER_MODEL,
            language=req.language, audio_track=req.audio_track,
        )
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = result.to_dict()
    if req.remove_fillers:
        payload["filler_intervals"] = [
            [round(s, 3), round(e, 3)]
            for s, e in transcribe_mod.filler_intervals(result.words)
        ]
    return payload


@app.get("/media/{name}")
def preview_media(name: str) -> FileResponse:
    """Stream an uploaded file for local preview."""
    path = _safe_upload_path(name)
    suffix = path.suffix.lower()
    media_type = {"mp4": "video/mp4", "mkv": "video/x-matroska", "mov": "video/quicktime"}.get(
        suffix.lstrip("."), "application/octet-stream"
    )
    return FileResponse(str(path), media_type=media_type)


@app.get("/download/{name}")
def download(name: str) -> FileResponse:
    safe_name = Path(name).name
    path = (config.OUTPUTS_DIR / safe_name).resolve()
    if config.OUTPUTS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output not found.")
    return FileResponse(str(path), filename=safe_name, media_type="video/mp4")


@app.exception_handler(media.MediaError)
def media_error_handler(_request, exc: media.MediaError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def main() -> None:
    import uvicorn

    uvicorn.run("precutter.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()