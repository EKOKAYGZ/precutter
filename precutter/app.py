"""FastAPI application for PreCutter."""
import logging
import os
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, media, render, segments, settings, silence
from . import events as events_mod


class _QuietProbeFilter(logging.Filter):
    """Drop access-log lines for external probes (e.g. /v1/models).

    Something on the machine polls OpenAI-style endpoints on every port;
    it is not our traffic and only spams the log.
    """
    BLOCKED = ("/v1/models", "/.well-known/appspecific/com.chrome.devtools.json")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        return not any(path in message for path in self.BLOCKED)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn configures its own logging at startup (dictConfig), which can
    # drop filters attached earlier in main(). Installing here runs after
    # logging setup, so the filter reliably sticks.
    logging.getLogger("uvicorn.access").addFilter(_QuietProbeFilter())
    yield


app = FastAPI(title="PreCutter", version="0.6.0", lifespan=lifespan)
config.ensure_dirs()
settings.init()

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


class ProcessRequest(BaseModel):
    filename: str
    threshold_db: float = Field(default=config.THRESHOLD_DB, ge=-60, le=-10)
    min_silence: float = Field(default=config.MIN_SILENCE, ge=0.2, le=3.0)
    padding_pre: float = Field(default=config.PADDING_PRE, ge=0.0, le=1.0)
    padding_post: float = Field(default=config.PADDING_POST, ge=0.0, le=1.0)
    min_keep: float = Field(default=config.MIN_KEEP, ge=0.1, le=2.0)
    audio_track: int = Field(default=0, ge=0)
    audio_channel: Optional[int] = Field(default=None, ge=0, le=7)
    # Tek analiz: dolgu kesme ve altyazı, transkripti paylaşan iki seçenek.
    remove_fillers: bool = False
    make_subtitles: bool = False
    # v0.4: LLM önem puanlama ile düşük skorlu bölümleri kes (Ollama).
    ai_cut: bool = False
    ai_threshold: Optional[int] = None
    # None -> o an geçerli config.WHISPER_MODEL kullanılır. Sınıf gövdesinde
    # sabit varsayılan almak, ayarlar sonradan değişince bayat kalıyordu.
    whisper_model: Optional[str] = None
    whisper_language: Optional[str] = None
    manual_segments: Optional[List[List[float]]] = None


class TranscribeRequest(BaseModel):
    filename: str
    model: Optional[str] = None
    language: Optional[str] = None
    remove_fillers: bool = False
    audio_track: int = Field(default=0, ge=0)


def _whisper_model(req) -> str:
    """Geçerli Whisper modeli: istekteki değer yoksa canlı config."""
    return getattr(req, "whisper_model", None) or getattr(req, "model", None) \
        or config.WHISPER_MODEL


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


def _analyze_file(path: Path, req: ProcessRequest, progress=None) -> tuple[float, List[list], dict]:
    """Tek analiz: sessizlik taraması + (istenirse) transkript tabanlı kesimler.

    progress, verilirse progress(stage, done, total) olarak çağrılır; stage
    "silence" (sessizlik taraması) veya "transcribe" (Whisper) olur. Böylece
    uzun transkriptler arayüzde yüzdeyle akar.
    """

    def stage(name: str, done: int, total: Optional[int]) -> None:
        if progress is not None:
            progress(name, done, total)

    duration = media.get_duration(path)
    _check_duration(duration)
    _check_audio_selection(path, req.audio_track, req.audio_channel)
    want_transcript = req.remove_fillers or req.make_subtitles or req.ai_cut
    transcript = None
    highlights: list = []
    ai_cuts: list = []
    ai_scores: list = []
    ai_cut_count = 0
    ai_source = "off"
    content = {"label": "general video", "notes": "", "model": None}
    if req.manual_segments:
        # Kullanıcı zaman çizelgesinde elle düzenledi: tespit atlanır,
        # liste kare ızgarasına oturtulup özetlenir.
        keep = segments.filter_short(
            segments.merge_segments([
                (max(0.0, float(s)), min(duration, float(e)))
                for s, e in req.manual_segments
                if float(e) > float(s)
            ]),
            req.min_keep,
        )
        filler_count = 0
        transcription_seconds = 0.0
    else:
        stage("silence", 0, 1)
        silences = silence.detect_silence(
            path, req.threshold_db, req.min_silence, duration,
            audio_track=req.audio_track, channel=req.audio_channel,
        )
        stage("silence", 1, 1)
        keep = segments.build_segments(
            silences, duration, req.padding_pre, req.padding_post,
            req.min_keep, config.MERGE_GAP,
        )
        filler_count = 0
        transcription_seconds = 0.0
        if want_transcript:
            from . import transcribe as transcribe_mod

            transcript, filler_count, transcription_seconds = _transcript_for(
                transcribe_mod, path, req, stage
            )
            if req.remove_fillers:
                keep = segments.subtract_segments(
                    keep, transcribe_mod.filler_intervals(transcript.words)
                )
                keep = segments.filter_short(segments.merge_segments(keep), req.min_keep)
        # v0.3 ses olayları (transkript bağlamıyla puanlanır).
        stage("events", 0, 1)
        highlights = _detect_highlights(
            path, req, duration,
            speech=getattr(transcript, "speech", []) or [],
            music=getattr(transcript, "music", []) or [],
            on_stage=None)
        stage("events", 1, 1)
        # v0.4 AI önem puanlama (transkript şart; kareler içeriği tanır).
        if req.ai_cut and transcript is not None:
            from . import frames as frames_mod
            from . import score as score_mod
            from . import transcribe as transcribe_mod

            threshold = req.ai_threshold or config.AI_THRESHOLD
            try:
                fp = transcribe_mod.file_fingerprint(path)
            except OSError:
                fp = ""
            try:
                content = frames_mod.classify_content(path, duration, fp or path.name)
            except Exception:
                content = {"label": "general video", "notes": "", "model": None}
            label = content.get("label") or "general video"
            if content.get("notes"):
                label += f" ({content['notes']})"

            def ai_progress(done: int, total: int) -> None:
                stage("ai", done, total)

            scored = score_mod.score_segments(
                transcript.words, keep, transcript.music or [], highlights,
                transcript.language, label, progress=ai_progress)
            ai_scores = scored["scores"]
            ai_source = scored["source"]
            ai_cuts = score_mod.cuts_below_threshold(ai_scores, threshold)
            if ai_cuts:
                keep = segments.subtract_segments(keep, ai_cuts)
                keep = segments.filter_short(
                    segments.merge_segments(keep), req.min_keep)
            ai_cut_count = len(ai_cuts)
    try:
        fps = media.get_fps(path)
    except media.MediaError:
        fps = 0.0
    if fps > 0:
        keep = segments.snap_to_frames(keep, fps, duration)
    summary = segments.summarize(duration, keep)
    summary["estimated_render_seconds"] = _estimate_render_seconds(
        summary, transcription_seconds
    )
    summary["filler_count"] = filler_count
    summary["ai_cut_count"] = ai_cut_count
    summary["ai_source"] = ai_source
    summary["ai_model"] = config.AI_MODEL
    summary["content_label"] = content.get("label")
    # Alt çizgili anahtarlar iç taşıma içindir; job sonucu yazılmadan pop'lanır.
    summary["_highlights"] = highlights
    summary["_ai_cuts"] = ai_cuts
    summary["_scores"] = ai_scores
    summary["_content"] = content
    return duration, [[round(s, 3), round(e, 3)] for s, e in keep], summary


def _transcript_for(transcribe_mod, path: Path, req: ProcessRequest, stage=None):
    """Transcript (cache varsa Whisper koşmaz). Returns (tr, filler_count, secs).

    Raises MediaError with an actionable message when Whisper is unavailable
    and no cached transcript exists.
    """
    import time

    t0 = time.time()
    model = _whisper_model(req)
    cached = transcribe_mod.load_cache(
        path, model, req.whisper_language, req.audio_track
    )
    if cached is not None:
        result = transcribe_mod._transcript_from_dict(cached)
    else:
        def on_progress(done: int, total: int) -> None:
            if stage is not None:
                stage("transcribe", done, total)

        try:
            result = transcribe_mod.transcribe_file(
                path,
                model_size=model,
                language=req.whisper_language,
                audio_track=req.audio_track,
                progress=on_progress if stage is not None else None,
            )
        except media.MediaError as exc:
            if "not installed" in str(exc):
                raise media.MediaError(
                    "Filler/subtitle needs Whisper (faster-whisper/torch), which "
                    "is not installed and no cached transcript exists. Install "
                    "requirements or turn those options off."
                ) from exc
            raise
    return result, len(result.fillers), time.time() - t0


def _estimate_render_seconds(summary: dict, transcription_seconds: float = 0.0) -> float:
    """Heuristic render-time estimate: re-encode cost scales with kept duration.

    Adds measured transcription time when Whisper had to run (0 on cache hit).
    """
    new_duration = float(summary.get("new_duration", 0.0))
    segment_count = int(summary.get("segment_count", 0))
    estimate = 2.0 + new_duration * 0.4 + segment_count * 0.15 + transcription_seconds
    return round(estimate, 1)


@app.middleware("http")
async def log_requests(request, call_next):
    # Health yoklaması hariç her isteğin girişini yaz: bir istek
    # hiç gelmediyse mi, gelip yarıda mı öldü hep belli olsun.
    if request.url.path != "/health":
        print(f"--> {request.method} {request.url.path}", flush=True)
    response = await call_next(request)
    return response


@app.get("/")
def index() -> FileResponse:
    # HTML kabuğu her zaman taze gelmeli; aksi halde eski sayfa + yeni JS
    # karışıp butonlar ölü olur. JS/CSS zaten sürümlü URL'lerle önbellekli.
    return FileResponse(
        str(Path(__file__).parent / "static" / "index.html"),
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


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
    try:
        out = _describe_stored_file(destination, original, size_bytes)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    return out


def _describe_stored_file(destination: Path, original: str, size_bytes: int) -> dict:
    """Probe an already-stored file and return the /upload-shaped payload."""
    duration = _probe_duration_best_effort(destination)
    if duration is not None and duration > config.MAX_VIDEO_DURATION:
        raise HTTPException(
            status_code=413,
            detail=f"Video too long. Maximum is {config.MAX_VIDEO_DURATION / 3600:.0f}h.",
        )
    try:
        streams = media.audio_streams(destination, include_loudness=False)
    except media.MediaError:
        streams = []
    return {
        "filename": destination.name,
        "original_name": original,
        "size_bytes": size_bytes,
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "audio_streams": streams,
        "suggested_mic": media.suggest_mic_track(streams),
    }


class ImportRequest(BaseModel):
    path: str


@app.post("/import")
def import_local(req: ImportRequest) -> dict:
    """Use a file already on this machine without uploading it again.

    Same volume -> hardlink (instant, no copy); otherwise a plain local
    copy (still faster than multipart HTTP). The user's original is never
    modified or deleted.
    """
    raw = (req.path or "").strip().strip("\"").strip("'")
    src = Path(raw)
    if not raw or not src.is_absolute():
        raise HTTPException(status_code=400, detail="Give an absolute file path.")
    if not src.is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {raw}")
    suffix = src.suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}.",
        )
    try:
        size_bytes = src.stat().st_size
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}") from exc
    if size_bytes > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum is {config.MAX_UPLOAD_BYTES / 1024**3:.0f} GB.",
        )
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = config.UPLOADS_DIR / stored_name
    try:
        os.link(src, destination)
    except OSError:
        try:
            shutil.copyfile(src, destination)
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"Could not link file: {exc}") from exc
    try:
        out = _describe_stored_file(destination, src.name, size_bytes)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    return out


@app.post("/analyze")
def analyze(req: ProcessRequest) -> dict:
    """Start the single analysis as a background job; poll GET /jobs/{job_id}.

    One pass does everything: silence detection always, and — when filler
    removal or subtitles are requested — Whisper transcription with live
    per-chunk progress. Filler removal is thus an option of the one analysis,
    never a second pass.
    """
    path = _safe_upload_path(req.filename)
    try:
        duration = media.get_duration(path)
        _check_duration(duration)
        _check_audio_selection(path, req.audio_track, req.audio_channel)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _prune_jobs_locked(time.time())
        _jobs[job_id] = {"status": "working", "stage": "queued", "done": 0,
                         "total": None, "created": time.time()}
    threading.Thread(
        target=_run_analyze_job, args=(job_id, path, req.model_dump()), daemon=True
    ).start()
    return {"job_id": job_id}


def _run_analyze_job(job_id: str, path: Path, req_data: dict) -> None:
    try:
        req = ProcessRequest(**req_data)

        def on_stage(name: str, done: int, total: Optional[int]) -> None:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job.update(status="working", stage=name, done=done, total=total)

        with _HEAVY_SEM:
            duration, keep, summary = _analyze_file(path, req, progress=on_stage)
            ai_cuts = summary.pop("_ai_cuts", [])
            highlights = summary.pop("_highlights", [])
            scores = summary.pop("_scores", [])
            content = summary.pop("_content", {"label": "general video"})
            overlays = _analysis_overlays(path, req, keep, duration, ai_cuts)
    except media.MediaError as exc:
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=str(exc))
        return
    except Exception as exc:  # unexpected: keep the message, never hang the poll
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=f"Analysis failed: {exc}")
        return
    with _jobs_lock:
        _jobs[job_id].update(
            status="done", done=1, total=1,
            result={"duration": round(duration, 3), "segments": keep,
                    "summary": summary, "cuts": overlays["cuts"],
                    "music": overlays["music"], "fps": overlays["fps"],
                    "highlights": highlights, "scores": scores,
                    "content": content,
                    "transcript": overlays["transcript"]},
        )


def _detect_highlights(path: Path, req: ProcessRequest, duration: float,
                       speech=None, music=None, on_stage=None) -> list:
    """v0.3 ses olayları. Asla analizi batırmaz: hata -> boş liste."""
    if on_stage is not None:
        on_stage("events", 0, 1)
    try:
        out = events_mod.analyze_events(
            path, req.audio_track, duration,
            speech=speech or [], music=music or [])
    except Exception:
        out = []
    if on_stage is not None:
        on_stage("events", 1, 1)
    return out


def _analysis_overlays(path: Path, req: ProcessRequest,
                       keep: List[list], duration: float,
                       ai_cuts: Optional[List[list]] = None) -> dict:
    """Editor coloring: cut regions by reason + music strip + source fps.

    Silence = complement of keep; filler/AI = their cut ranges; music and
    subtitle availability come from the cached transcript.
    """
    keep_t = [(float(s), float(e)) for s, e in keep]
    cuts = [{"start": s, "end": e, "reason": "silence"}
            for s, e in segments.complement(keep_t, duration)]
    music: List[list] = []
    transcript = {"available": False, "language": None, "filler_count": 0,
                  "filler_ratio": 0.0, "word_count": 0}
    if req.remove_fillers or req.make_subtitles:
        try:
            from . import transcribe as transcribe_mod

            cached = transcribe_mod.load_cache(
                path, _whisper_model(req), req.whisper_language, req.audio_track)
            if cached is not None:
                result = transcribe_mod._transcript_from_dict(cached)
                if req.remove_fillers:
                    cuts = _relabel_filler_cuts(
                        cuts, transcribe_mod.filler_intervals(result.words))
                if ai_cuts:
                    cuts = _relabel_ai_cuts(cuts, ai_cuts)
                music = [[round(s, 3), round(e, 3)]
                         for s, e in (result.music or [])]
                transcript = {
                    "available": True,
                    "language": result.language,
                    "filler_count": len(result.fillers),
                    "filler_ratio": round(float(result.filler_ratio or 0.0), 4),
                    "word_count": len(result.words),
                }
        except media.MediaError:
            pass
    try:
        fps = media.get_fps(path)
    except media.MediaError:
        fps = 0.0
    return {"cuts": cuts, "music": music, "fps": round(fps, 3) if fps else 0.0,
            "transcript": transcript}


def _relabel_ai_cuts(cuts: List[dict], ai_cuts: List[list]) -> List[dict]:
    """Mark complement pieces overlapping AI low-score ranges as AI cuts."""
    out = []
    for cut in cuts:
        s, e = cut["start"], cut["end"]
        if any(float(a[0]) < e and float(a[1]) > s for a in (ai_cuts or [])):
            out.append({"start": s, "end": e, "reason": "ai"})
        else:
            out.append(cut)
    return out


def _relabel_filler_cuts(cuts: List[dict], fills: List[tuple]) -> List[dict]:
    """Mark complement pieces overlapping filler ranges as filler cuts."""
    out = []
    for cut in cuts:
        s, e = cut["start"], cut["end"]
        if any(fs < e and fe > s for fs, fe in fills):
            out.append({"start": s, "end": e, "reason": "filler"})
        else:
            out.append(cut)
    return out


@app.post("/render")
def render_video(req: ProcessRequest) -> dict:
    """Start a render in the background; poll GET /jobs/{job_id} for progress.

    Long renders (tens of minutes) would otherwise outlive the HTTP connection
    and surface as an opaque "Failed to fetch" in the browser.
    """
    path = _safe_upload_path(req.filename)
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _prune_jobs_locked(time.time())
        _jobs[job_id] = {"status": "working", "stage": "queued", "done": 0,
                         "total": None, "created": time.time()}
    thread = threading.Thread(
        target=_run_render_job, args=(job_id, path, req.model_dump()), daemon=True
    )
    thread.start()
    return {"job_id": job_id}


def _run_render_job(job_id: str, path: Path, req_data: dict) -> None:
    try:
        req = ProcessRequest(**req_data)
        # Ağır iş sırası: başka bir render/transkript bitene kadar bekle.
        with _HEAVY_SEM:
            with _jobs_lock:
                _jobs[job_id].update(stage="analyze", done=0, total=None)
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
            render.render(path, segments, output_path, progress=on_progress,
                          mic_track=req.audio_track)
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

# Ağır iş disiplini: render (ffmpeg) ve transkript (whisper) aynı anda
# koşarsa CPU/RAM yarışı sunucuyu öldürüyor (bkz. çift Whisper olayı).
# Global semaphore ile günde 1 ağır iş işler; diğerleri "queued"da bekler.
_HEAVY_SEM = threading.Semaphore(1)

# Tek-uçuş transkript: aynı (dosya, model, dil, iz) için çalışan iş varsa
# yeni istek aynı job_id'yi alır; ikinci Whisper asla başlamaz.
_transcribe_keys: Dict[str, str] = {}

# Bitmiş işler bu süreden sonra _jobs'tan temizlenir.
_JOB_TTL_SECONDS = 3600.0


def _prune_jobs_locked(now: float) -> None:
    stale = [
        jid for jid, job in _jobs.items()
        if job.get("status") in ("done", "error")
        and now - job.get("created", now) > _JOB_TTL_SECONDS
    ]
    for jid in stale:
        _jobs.pop(jid, None)


@app.get("/jobs/{job_id}")
def render_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job_id, **job}


@app.get("/browse")
def browse(path: Optional[str] = None) -> dict:
    """Server-side file picker: list drives/dirs + video files.

    No path -> filesystem roots (Windows drives). Directories first,
    then .mp4/.mkv/.mov files with size + mtime. Used by the UI so big
    local files link via /import instead of uploading.
    """
    import string as _string

    if not path:
        roots = [f"{d}:\\" for d in _string.ascii_uppercase
                 if Path(f"{d}:\\").exists()]
        home = str(Path.home())
        return {"cwd": None, "parent": None, "roots": roots,
                "dirs": [], "files": [],
                "home": home if Path(home).exists() else None}
    base = Path(path)
    if not base.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory.")
    try:
        entries = list(base.iterdir())
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot list: {exc}") from exc
    dirs, files = [], []
    for entry in entries:
        try:
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
            elif (entry.is_file()
                    and entry.suffix.lower() in config.ALLOWED_EXTENSIONS):
                st = entry.stat()
                files.append({"name": entry.name, "path": str(entry),
                              "size_bytes": st.st_size, "mtime": st.st_mtime})
        except OSError:
            continue
    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["name"].lower())
    parent = str(base.parent) if base.parent != base else None
    return {"cwd": str(base), "parent": parent, "roots": [],
            "dirs": dirs, "files": files, "home": None}


@app.get("/waveform/{name}")
def waveform(name: str, track: int = 0, peaks: int = 1200) -> dict:
    """Per-track waveform peaks for the lane canvases (cached JSON).

    Decodes the track to 8 kHz mono and stores abs-peak per bucket.
    """
    path = _safe_upload_path(name)
    if track < 0:
        raise HTTPException(status_code=400, detail="Invalid track.")
    peaks = max(100, min(int(peaks), 4000))
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
    cached = previews / f"{path.stem}_t{track}_wf{peaks}.json"
    if cached.exists():
        try:
            import json as _json

            return _json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    import subprocess as _sp

    import numpy as _np

    cmd = [config.FFMPEG_BIN, "-hide_banner", "-nostats", "-i", str(path),
           "-map", f"0:a:{track}", "-ac", "1", "-ar", "8000",
           "-f", "s16le", "-c:a", "pcm_s16le", "-"]
    try:
        result = _sp.run(cmd, capture_output=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail="ffmpeg not found.") from exc
    if result.returncode != 0 or not result.stdout:
        raise HTTPException(status_code=400, detail="Could not read audio.")
    samples = _np.frombuffer(result.stdout, dtype=_np.int16).astype(_np.float32) / 32768.0
    buckets = _np.array_split(_np.abs(samples), peaks)
    out = [round(float(b.max()) if b.size else 0.0, 4) for b in buckets]
    payload = {"peaks": out, "count": len(out), "track": track,
               "sample_rate": 8000}
    try:
        import json as _json

        cached.write_text(_json.dumps(payload), encoding="utf-8")
    except OSError:
        pass
    return payload


@app.get("/preview-mix/{name}")
def preview_mix(name: str, tracks: str = "0", mic: int = 0) -> FileResponse:
    """Mixed preview of selected tracks (cached m4a) for mute/solo checking.

    tracks=csv of 0-based indices, mic gets a loudness boost. Used by the
    editor instead of juggling per-track elements.
    """
    path = _safe_upload_path(name)
    try:
        wanted = [int(x) for x in tracks.split(",") if x.strip() != ""]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tracks.") from None
    try:
        streams = media.audio_streams(path, include_loudness=False)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    wanted = [w for w in wanted if 0 <= w < len(streams)]
    if not wanted:
        raise HTTPException(status_code=400, detail="No valid tracks selected.")
    mic_idx = mic if mic in wanted else wanted[0]
    previews = config.WORKSPACE_DIR / "previews"
    previews.mkdir(parents=True, exist_ok=True)
    key = "_".join(str(w) for w in wanted)
    cached = previews / f"{path.stem}_mix_{key}_m{mic_idx}.m4a"
    if not cached.exists():
        import subprocess as _sp

        chains = []
        for w in wanted:
            vol = 1.5 if w == mic_idx else 1.0
            chains.append(f"[0:a:{w}]volume={vol}[m{w}]")
        chains.append("".join(f"[m{w}]" for w in wanted)
                      + f"amix=inputs={len(wanted)}:normalize=0[mixout]")
        cmd = [config.FFMPEG_BIN, "-hide_banner", "-y", "-i", str(path),
               "-filter_complex", ";".join(chains),
               "-map", "[mixout]", "-ac", "2",
               "-c:a", "aac", "-b:a", "128k", str(cached)]
        try:
            result = _sp.run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail="ffmpeg not found.") from exc
        if result.returncode != 0 or not cached.exists():
            raise HTTPException(status_code=400, detail="Could not mix preview.")
    return FileResponse(str(cached), media_type="audio/mp4")


@app.get("/preview-audio/{name}")
def preview_audio(name: str, track: int = 0, channel: Optional[str] = None) -> FileResponse:
    """Extract one audio track as a mono preview file (cached) for auditioning.

    channel "0"/"1" solos that stereo channel (mic often lives on one side);
    otherwise both channels are mixed down. Mono output plays centered, so a
    mic recorded on a single channel is clearly audible in VLC or the browser.
    """
    path = _safe_upload_path(name)
    if track < 0:
        raise HTTPException(status_code=400, detail="Invalid track.")
    solo: Optional[int] = None
    if channel is not None and channel != "mix":
        try:
            solo = int(channel)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid channel.") from None
        if solo < 0:
            raise HTTPException(status_code=400, detail="Invalid channel.")
    try:
        streams = media.audio_streams(path, include_loudness=False)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if track >= len(streams):
        raise HTTPException(
            status_code=400,
            detail=f"Audio track {track} not found. File has {len(streams)} track(s).",
        )
    if solo is not None and solo >= streams[track]["channels"]:
        raise HTTPException(
            status_code=400,
            detail=f"Channel {solo} not found on track {track}.",
        )
    previews = config.WORKSPACE_DIR / "previews"
    previews.mkdir(parents=True, exist_ok=True)
    suffix = f"_ch{solo}" if solo is not None else ""
    cached = previews / f"{path.stem}_t{track}{suffix}_mono.m4a"
    if not cached.exists():
        try:
            _build_preview_audio(path, track, solo, cached)
        except media.MediaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(str(cached), media_type="audio/mp4")


_proxy_jobs: Dict[str, str] = {}


class ProxyRequest(BaseModel):
    filename: str


@app.post("/proxy")
def start_proxy(req: ProxyRequest) -> dict:
    """Build lightweight preview proxies in the background (job + progress).

    Same file twice -> the running job is returned (single-flight).
    """
    path = _safe_upload_path(req.filename)
    stem = path.stem
    with _jobs_lock:
        _prune_jobs_locked(time.time())
        old = _proxy_jobs.get(stem)
        if old is not None and _jobs.get(old, {}).get("status") == "working":
            return {"job_id": old, "deduped": True}
        job_id = uuid.uuid4().hex
        _jobs[job_id] = {"status": "working", "stage": "queued", "done": 0,
                         "total": None, "created": time.time()}
        _proxy_jobs[stem] = job_id
    threading.Thread(target=_run_proxy_job, args=(job_id, path), daemon=True).start()
    return {"job_id": job_id}


def _run_proxy_job(job_id: str, path: Path) -> None:
    from . import proxy as proxy_mod

    def _set(stage: str, done: int, total: int) -> None:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(status="working", stage=stage, done=done, total=total)

    try:
        with _HEAVY_SEM:
            try:
                streams = media.audio_streams(path, include_loudness=False)
            except media.MediaError as exc:
                raise media.MediaError(f"No audio: {exc}") from exc
            tracks = list(range(len(streams)))
            total = len(tracks) + 1
            outdir = proxy_mod.proxy_dir(path.stem)
            for i, track in enumerate(tracks):
                _set("proxy-audio", i, total)
                try:
                    proxy_mod.build_track_audio(path, track, outdir)
                except media.MediaError:
                    pass
            _set("proxy-video", len(tracks), total)
            try:
                proxy_mod.build_video_proxy(path, outdir)
            except media.MediaError:
                pass
            result = proxy_mod.status(path.stem, tracks)
    except media.MediaError as exc:
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=str(exc))
        return
    except Exception as exc:
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=f"Proxy failed: {exc}")
        return
    with _jobs_lock:
        _jobs[job_id].update(status="done", done=1, total=1, result=result)


@app.get("/proxy/{name}")
def proxy_status(name: str) -> dict:
    """Proxy files available right now (no building). 404 = never started."""
    path = _safe_upload_path(name)
    with _jobs_lock:
        job_id = _proxy_jobs.get(path.stem)
        running = (job_id is not None
                   and _jobs.get(job_id, {}).get("status") == "working")
    try:
        n = len(media.audio_streams(path, include_loudness=False))
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from . import proxy as proxy_mod

    out = proxy_mod.status(path.stem, list(range(n)))
    out["building"] = running
    out["job_id"] = job_id
    return out


def _proxy_file_or_404(name: str, track: Optional[int] = None):
    from . import proxy as proxy_mod

    path = _safe_upload_path(name)
    outdir = config.WORKSPACE_DIR / "previews" / path.stem
    if track is None:
        cand = outdir / "proxy.mp4"
        if not cand.exists():
            raise HTTPException(status_code=404, detail="Proxy video not ready.")
        return FileResponse(str(cand), media_type="video/mp4")
    for suffix, mt in ((".ogg", "audio/ogg"), (".m4a", "audio/mp4")):
        cand = outdir / f"track{track}{suffix}"
        if cand.exists() and cand.stat().st_size > 1024:
            return FileResponse(str(cand), media_type=mt)
    raise HTTPException(status_code=404, detail="Proxy audio not ready.")


@app.get("/proxy-audio/{name}")
def proxy_audio(name: str, track: int = 0):
    """Cached per-track proxy audio (Range-capable). 404 while building."""
    if track < 0:
        raise HTTPException(status_code=400, detail="Invalid track.")
    return _proxy_file_or_404(name, track)


@app.get("/proxy-video/{name}")
def proxy_video(name: str):
    """Cached 720p proxy video (Range-capable). 404 while building."""
    return _proxy_file_or_404(name, None)


def _build_preview_audio(path: Path, track: int, solo: Optional[int], cached: Path) -> None:
    """Tek izin mono önizlemesini üret (yoksa). Hata -> MediaError."""
    import subprocess as _sp

    filt = f"pan=mono|c0=c{solo}," if solo is not None else ""
    cmd = [
        config.FFMPEG_BIN, "-hide_banner", "-y",
        "-i", str(path),
        "-map", f"0:a:{track}",
        "-af", f"{filt}aresample=async=1",
        "-ac", "1",
        "-c:a", "aac", "-b:a", "96k",
        str(cached),
    ]
    try:
        result = _sp.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise media.MediaError("ffmpeg not found.") from exc
    if result.returncode != 0 or not cached.exists():
        raise media.MediaError("Could not extract audio preview.")


@app.get("/settings")
def get_settings() -> dict:
    return settings.load()


@app.put("/settings")
def put_settings(patch: dict) -> dict:
    try:
        return settings.save(patch or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.delete("/uploads/{name}")
def delete_upload(name: str) -> dict:
    """Delete an uploaded file and its cached audio previews."""
    path = _safe_upload_path(name)
    freed = path.stat().st_size if path.exists() else 0
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete: {exc}") from exc
    previews = config.WORKSPACE_DIR / "previews"
    for cached in list(previews.glob(f"{path.stem}_t*.m4a")) + list(
            previews.glob(f"{path.stem}_mix_*.m4a")) + list(
            previews.glob(f"{path.stem}_t*_wf*.json")):
        try:
            freed += cached.stat().st_size
            cached.unlink(missing_ok=True)
        except OSError:
            pass
    return {"deleted": path.name, "freed_bytes": freed}


@app.post("/storage/clear")
def clear_storage(payload: dict | None = None) -> dict:
    """Delete cached/generated files. target 'cache' keeps uploads/outputs."""
    target = (payload or {}).get("target", "all")
    freed = 0
    targets = [config.WORKSPACE_DIR / "previews"]
    if target != "cache":
        targets = [config.UPLOADS_DIR, config.OUTPUTS_DIR] + targets
    for directory in targets:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_file() and path.name != ".gitkeep":
                try:
                    freed += path.stat().st_size
                    path.unlink()
                except OSError:
                    pass
    try:
        from . import transcribe as transcribe_mod

        cache = transcribe_mod.cache_dir()
        for path in cache.glob("*.json"):
            try:
                freed += path.stat().st_size
                path.unlink()
            except OSError:
                pass
    except (ImportError, OSError):
        pass
    return {"freed_bytes": freed, "target": target}


@app.post("/streams")
def streams(req: TranscribeRequest) -> dict:
    """List audio tracks/channels so the UI can offer a source selector."""
    path = _safe_upload_path(req.filename)
    try:
        duration = media.get_duration(path)
        tracks = media.audio_streams(path)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        suggestion = media.suggest_mic_with_confidence(path, tracks)
    except media.MediaError:
        suggestion = None
    if suggestion is None:
        legacy = media.suggest_mic_track(tracks)
        suggestion = {"track": legacy, "confidence": 0.4} if legacy is not None else None
    return {
        "duration": round(duration, 3),
        "audio_streams": tracks,
        "suggested_mic": suggestion["track"] if suggestion else None,
        "suggested_mic_confidence": suggestion["confidence"] if suggestion else None,
    }


@app.post("/transcribe")
def transcribe(req: TranscribeRequest) -> dict:
    """Start transcription in the background; poll GET /jobs/{job_id}.

    A 40-minute file keeps Whisper busy for many minutes; a hanging
    request looks frozen and risks duplicate runs. Jobs report per-chunk
    progress instead. Identical requests (same file/model/language/track)
    join the already-running job instead of starting a second Whisper.
    """
    path = _safe_upload_path(req.filename)
    try:
        duration = media.get_duration(path)
        _check_duration(duration)
        _check_audio_selection(path, req.audio_track, None)
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    key = _transcribe_key(path, req)
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        running_id = _transcribe_keys.get(key)
        running = _jobs.get(running_id) if running_id else None
        if running is not None and running.get("status") == "working":
            # Aynı iş zaten koşuyor: ikinci Whisper'i başlatma, ona katıl.
            return {"job_id": running_id, "deduped": True}
        _prune_jobs_locked(time.time())
        _jobs[job_id] = {"status": "working", "stage": "queued", "done": 0,
                         "total": None, "created": time.time()}
        _transcribe_keys[key] = job_id
    thread = threading.Thread(
        target=_run_transcribe_job, args=(job_id, path, req.model_dump()), daemon=True
    )
    thread.start()
    return {"job_id": job_id, "deduped": False}


def _transcribe_key(path: Path, req: TranscribeRequest) -> str:
    return (f"{path.resolve()}|{req.model or config.WHISPER_MODEL}"
            f"|{req.language}|{req.audio_track}")


def _run_transcribe_job(job_id: str, path: Path, req_data: dict) -> None:
    from . import transcribe as transcribe_mod

    key = _transcribe_key(path, TranscribeRequest(**req_data))
    try:
        req = TranscribeRequest(**req_data)
        # Ağır iş sırası: başka bir render/transkript bitene kadar bekle.
        with _HEAVY_SEM:
            with _jobs_lock:
                _jobs[job_id].update(stage="transcribe", done=0, total=None)

            def on_progress(done: int, total: int) -> None:
                with _jobs_lock:
                    job = _jobs.get(job_id)
                    if job is not None:
                        job.update(status="working", stage="transcribe",
                                   done=done, total=total)

            result = transcribe_mod.transcribe_file(
                path, model_size=req.model or config.WHISPER_MODEL,
                language=req.language, audio_track=req.audio_track,
                progress=on_progress,
            )
    except media.MediaError as exc:
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=str(exc))
        return
    except Exception as exc:  # unexpected: keep the message, never hang the poll
        with _jobs_lock:
            _jobs[job_id].update(status="error", error=f"Transcription failed: {exc}")
        return
    finally:
        with _jobs_lock:
            if _transcribe_keys.get(key) == job_id:
                _transcribe_keys.pop(key, None)
    payload = result.to_dict()
    if req.remove_fillers:
        payload["filler_intervals"] = [
            [round(s, 3), round(e, 3)]
            for s, e in transcribe_mod.filler_intervals(result.words)
        ]
    with _jobs_lock:
        _jobs[job_id].update(status="done", result=payload)


class SrtRequest(BaseModel):
    filename: str
    segments: List[List[float]]
    audio_track: int = Field(default=0, ge=0)
    model: Optional[str] = None
    language: Optional[str] = None


@app.post("/srt")
def export_srt(req: SrtRequest):
    """Transcript remapped onto the cut timeline, as an SRT download.

    Uses the transcript cached by the analysis job only — it never kicks off
    Whisper inside a request (that is what made the old endpoint look hung).
    """
    from fastapi.responses import PlainTextResponse

    from . import transcribe as transcribe_mod

    path = _safe_upload_path(req.filename)
    keep = [(float(s), float(e)) for s, e in req.segments if float(e) > float(s)]
    try:
        _check_audio_selection(path, req.audio_track, None)
        cached = transcribe_mod.load_cache(
            path, req.model or config.WHISPER_MODEL, req.language, req.audio_track)
        if cached is None:
            raise HTTPException(
                status_code=409,
                detail="No transcript yet. Turn on subtitles (or filler removal) "
                       "and run Analyze first.",
            )
        words = transcribe_mod._transcript_from_dict(cached).words
    except media.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    srt = transcribe_mod.build_srt(words, keep)
    name = f"{path.stem}_cut.srt"
    return PlainTextResponse(srt, media_type="text/plain; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


class ChatRequest(BaseModel):
    filename: str
    message: str
    history: Optional[List[Dict[str, str]]] = None
    audio_track: int = Field(default=0, ge=0)


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    """Video hakkında soru-cevap (AI sekmesi). Transkript + skor bağlamlı."""
    from . import score as score_mod

    path = _safe_upload_path(req.filename)
    msg = (req.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Empty message.")
    host = (config.OLLAMA_HOST or "http://127.0.0.1:11434").rstrip("/")
    model = config.AI_MODEL or score_mod.AI_MODEL_DEFAULT
    context = _chat_context(path, req, msg)
    try:
        reply = score_mod.answer_chat(
            host, model, context, req.history or [], msg)
    except media.MediaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"reply": reply, "model": model}


def _chat_context(path: Path, req: ChatRequest, msg: str) -> str:
    """Transkriptten soruyla ilgili parçalar + skor özeti."""
    from . import transcribe as transcribe_mod

    lines: List[str] = []
    try:
        duration = media.get_duration(path)
        lines.append(f"Video: {path.name}, duration {duration:.0f}s.")
    except media.MediaError:
        pass
    try:
        cached = transcribe_mod.load_cache(
            path, config.WHISPER_MODEL, None, req.audio_track)
    except media.MediaError:
        cached = None
    if cached is None:
        return "\n".join(lines) + "\nNo transcript yet. Analyze the video first."
    result = transcribe_mod._transcript_from_dict(cached)
    lines.append(f"Language: {result.language}.")
    words = result.words
    # Soru kelimeleriyle örtüşen 60 sn pencereler, yoksa baştan.
    tokens = {w.lower() for w in msg.split() if len(w) > 3}
    buckets: Dict[int, List] = {}
    for w in words:
        buckets.setdefault(int(w.start // 60), []).append(w)
    ranked = sorted(
        buckets.items(),
        key=lambda kv: -sum(1 for w in kv[1] if w.text.lower() in tokens))
    picked = [kv[1] for kv in ranked[:3] if kv[1]]
    if not picked:
        picked = [words[:150]]
    for win in picked:
        txt = " ".join(w.text for w in win[:200])
        lines.append(f"[{win[0].start:.0f}-{win[-1].end:.0f}s] {txt}")
    return "\n".join(lines)


@app.get("/doctor")
def doctor() -> dict:
    """Environment report: ffmpeg, NVENC, Whisper/CUDA, disk. Never throws."""
    import shutil as _shutil

    report: dict = {
        "ffmpeg": _shutil.which(config.FFMPEG_BIN) is not None,
        "ffprobe": _shutil.which(config.FFPROBE_BIN) is not None,
        "encoder": None,
        "nvenc": False,
        "torch": False,
        "cuda": False,
        "whisper": False,
        "whisper_device": None,
        "gpu_name": None,
        "cpu_count": None,
        "free_disk_gb": None,
        "ollama": False,
        "ollama_models": [],
        "ai_model": config.AI_MODEL,
    }
    try:
        import os as _os

        report["cpu_count"] = _os.cpu_count()
    except OSError:
        pass
    try:
        report["free_disk_gb"] = round(
            _shutil.disk_usage(config.WORKSPACE_DIR).free / 1024**3, 1)
    except OSError:
        pass
    if report["ffmpeg"]:
        try:
            report["encoder"] = media.encoder_name()
            report["nvenc"] = media.encoder_name() == "nvenc"
        except media.MediaError:
            pass
    try:
        import torch as _torch

        report["torch"] = True
        report["cuda"] = bool(_torch.cuda.is_available())
    except ImportError:
        pass
    try:
        import faster_whisper  # noqa: F401

        report["whisper"] = True
    except ImportError:
        pass
    try:
        from . import transcribe as _tr

        report["whisper_device"] = _tr.whisper_device()
        report["gpu_name"] = _tr.gpu_name() if report["whisper_device"] == "cuda" else None
    except Exception:
        report["whisper_device"] = None
        report["gpu_name"] = None
    report["ffmpeg_version"] = None
    if report["ffmpeg"]:
        try:
            import subprocess as _sp

            r = _sp.run([config.FFMPEG_BIN, "-hide_banner", "-version"],
                        capture_output=True, text=True)
            first = (r.stdout or "").splitlines()
            if first:
                report["ffmpeg_version"] = first[0].replace("ffmpeg version ", "")
        except OSError:
            pass
    try:
        from . import score as _score

        models = _score.installed_models()
        report["ollama"] = models is not None
        report["ollama_models"] = (models or [])[:12]
    except Exception:
        pass
    return report


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