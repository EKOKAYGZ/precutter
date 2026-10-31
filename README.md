# PreCutter v0.5

PreCutter is a local tool that removes silent parts from videos. It runs a small
FastAPI server that serves a plain HTML/CSS/JS web UI. Silence detection and
rendering are performed with `ffmpeg` / `ffprobe` via subprocess.

## Requirements

- Python 3.11+
- `ffmpeg` and `ffprobe` available on your `PATH`

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python -m precutter.app
```

The browser opens by itself; the app is served at http://127.0.0.1:8000.
Pass `--no-browser` (or set `PRECUTTER_NO_BROWSER=1`) to skip that.

### Windows: one-click launcher

- Double-click **`start.bat`** - it picks your Python (project `.venv` first),
  checks the requirements, starts the server and opens the browser. Press
  `Ctrl+C` in the server window (or close it) to stop.
- Double-click **`create-shortcut.bat`** once to put a **PreCutter** shortcut on
  your Desktop.
- Overrides: `PRECUTTER_PORT` (default `8000`; if it is busy the next free port
  is used), `PRECUTTER_HOST` (default `127.0.0.1`), `PRECUTTER_NO_BROWSER=1`.
  Starting it twice is safe - if PreCutter is already running, the browser is
  simply pointed at the running instance.

## Usage

1. Drop a `.mp4`, `.mkv`, or `.mov` file onto the page (or click to browse).
2. Adjust the sliders:
   - **Silence threshold** (-60..-10 dB) - noise floor used by `silencedetect`.
   - **Min silence** (0.2..3.0 s) - minimum silence length to cut.
   - **Padding** (0..0.5 s) - extra buffer kept around non-silent parts.
3. Click **Analyze** to see the timeline and duration summary.
4. Click **Render** to produce the processed video, then download it.

The timeline shows kept parts in blue and cut parts in gray.

## API

| Method | Path              | Description                          |
| ------ | ----------------- | ------------------------------------ |
| GET    | `/`               | Web UI                               |
| GET    | `/health`         | Tool status (`ffmpeg`/`ffprobe`)     |
| POST   | `/upload`         | Upload a video (multipart form)      |
| POST   | `/import`         | Link a local file by path (no copy)  |
| GET    | `/peaks-data/{name}?track=N` | WaveformData peaks for Peaks.js (cached) |
| GET    | `/browse`         | Server file picker (drives/dirs/videos) |
| POST   | `/analyze`        | Start analysis job (poll `/jobs`)    |
| POST   | `/streams`        | List audio tracks/channels of a file |
| GET    | `/projects`       | List uploaded project files          |
| GET    | `/media/{name}`   | Stream an upload for local preview   |
| POST   | `/transcribe`     | Start transcript job (poll `/jobs`)  |
| POST   | `/render`         | Start a background render job        |
| GET    | `/jobs/{job_id}`  | Job progress / result (analyze+render+transcribe) |
| GET    | `/preview-audio/{name}?track=N` | Extract one audio track for audition |
| GET    | `/preview-mix/{name}?tracks=0,1&mic=1` | Mixed preview for mute/solo check |
| GET    | `/waveform/{name}?track=N&peaks=M` | Waveform peaks JSON for the editor |
| POST   | `/srt`              | Cached transcript as SRT on the cut timeline (409 if none) |
| GET    | `/settings`       | Current app settings                 |
| PUT    | `/settings`       | Update app settings (no restart)     |
| DELETE | `/uploads/{name}` | Delete an upload + its previews      |
| POST   | `/storage/clear`  | Clear cache (`{"target":"cache"}`) or everything |
| GET    | `/doctor`         | Environment report (ffmpeg, NVENC, CUDA, disk) |
| GET    | `/download/{name}`| Download a rendered output           |

`/analyze` and `/render` accept JSON:

```json
{
  "filename": "<stored upload filename>",
  "threshold_db": -40,
  "min_silence": 0.8,
  "padding_pre": 0.2,
  "padding_post": 0.25,
  "min_keep": 0.3,
  "audio_track": 0,
  "audio_channel": null,
  "remove_fillers": false,
  "make_subtitles": false,
  "whisper_model": null,
  "whisper_language": null,
  "manual_segments": null
}
```
There is a single analysis pass. `POST /analyze` returns `{job_id}`
immediately; poll `GET /jobs/{job_id}` — stages are `queued`, then
`silence`, then (only when a transcript is needed) `transcribe` with
per-chunk `done`/`total`, then `done` with `duration`, `segments`,
`summary`, `cuts`, `music`, `fps`, and `transcript` (`available`,
`language`, `filler_count`, `filler_ratio`, `word_count`).

Filler removal is an option of that one analysis, not a second pass:
with `remove_fillers: true`, filler-word ranges from the transcript are
also cut out of the kept segments. With `make_subtitles: true` the same
transcript is produced (without changing cuts) so `/srt` can map it onto
the cut timeline afterwards. `whisper_model: null` means "use the live
server setting". The cached transcript (same model, language, track) is
reused, so Whisper only runs on a cache miss — and its measured time is
included in `estimated_render_seconds`. Without Whisper installed and no
cache, analyze fails with an actionable error instead.

Keep-segment bounds are snapped to the source video's frame grid before
rendering (and in the summary), so a 0.37 s part no longer becomes 0.4 s:
total output lands within 1 frame of the expected duration.

Errors are returned as JSON with a `detail` field.

`POST /render` returns `{job_id}` immediately and renders in a background
thread; poll `GET /jobs/{job_id}` for `{status, stage, done, total}` until
`status` is `done` (with `download_url` + `summary`) or `error`. This keeps
long renders from outliving the HTTP connection. `GET /preview-audio/{name}`
extracts one audio track as `.m4a` (cached under `workspace/previews/`) so
you can hear which track is the mic before analyzing.

`POST /import {"path": "C:\\Videos\\kayit.mp4"}` links a file that is
already on the server machine: same volume it becomes a hardlink
(instant, no copy), otherwise a plain local copy — both faster than a
multipart upload. The original is never modified. The web UI keeps the
selected file and the last analysis in `localStorage`, so a page refresh
restores them instead of starting over.

### v0.3 sound events (spikes → highlights)

Every analysis also spots loud sound events — screams, bursts, sudden
reactions — with no ML model (plain ffmpeg + numpy, runs on any CPU):

1. `precutter/events.py` decodes the reference track to 16 kHz mono and
   builds a 100 ms RMS loudness curve.
2. Spikes = buckets ≥12 dB above the trailing 5 s median (causal baseline,
   digital silence ignored, close bursts keep the loudest).
3. Each spike becomes a highlight candidate with 2 s tension padding
   before it and 1 s after; overlapping candidates merge.
4. Heuristic score 0–100: spike height tiers, loud-peak bonus, +10 with
   speech, −15 over music, −5 for long bursts.

`GET /jobs/{job_id}` analysis results carry `highlights`
(`start`/`end`/`peak_db`/`delta_db`/`score`/`reasons`), drawn as the
yellow strip under the timeline (opacity = score). Event spotting never
fails an analysis — on error it yields `[]`. PANNs/YAMNet labels
(`scream`, `laugh`) are future optional extras, never requirements.

### v0.4 AI importance scoring (Ollama, optional)

One model does vision AND scoring (`qwen3-vl:4b`, settings-changeable,
`think` off; GPU when Ollama has one, plain CPU otherwise). Slices: 1
frame every 2 minutes (min 4, max 24), 320px, from each slice's middle.
Each slice goes out as ONE call — frame + slice transcript + speech /
silence / music ratios — and comes back as
`{label, score, reason}` with labels `gameplay | talking-head |
static-screen | menu-loading | cutscene`. Music rule: audio says music
but words are present → speech with background music, no penalty.
Segment scores blend 0.5·LLM + 0.2·vision + 0.3·heuristic; parts below
`ai_threshold` (default 30) are cut. Any failure (model missing,
timeout, bad JSON, Ollama down) falls back — the SAME model scores the
transcript alone (vision off), then heuristic — the analysis still
completes and never demands a second model be installed. Slice and
score caches key on file hash + model name.

- `POST /analyze {"ai_cut": true, "ai_threshold": 30}` — needs a
  transcript, like fillers. Result adds `scores` (`start`/`end`/`score`/
  `reasons`), `content` (`label` like "Minecraft", `notes`), and summary
  fields `ai_cut_count`, `ai_source` (`llm`/`heuristic`/`off`), `ai_model`.
- `POST /chat {"filename", "message", "history?"}` — video Q&A over the
  transcript (keyword-retrieved windows). Needs `ollama serve` +
  `ollama pull qwen3-vl:4b`.
- Frames are optional context: slice labels feed the scoring prompt
  and PRE.AI chat (`[visual 0-120s] gameplay (90): rush`). Nothing
  auto-downloads, ever.
- `GET /doctor` reports `ollama`, `ollama_models`, `ai_model`.
- `PUT /settings` accepts `ollama_host`, `ai_model`, `ai_threshold`
  (10–70).
- `python scripts/benchmark.py [--models qwen3-vl:4b gemma3:4b qwen3:1.7b]`
  compares latency, JSON-valid rate and good-vs-bad spread on a fixed
  sample. Missing models are skipped.

Performance target: GPU when Ollama has one, plain CPU otherwise —
1.7B-class models run on both. Keep `SEGMENTS_PER_CALL` up and prompts
short; that is what keeps a 50-minute video in the minutes range.

### v0.6 view-only player (canvas lanes + overview)

Peaks.js was tried first (vendored 3.2.0, server-side WaveformData
endpoint) but dropped: too many version-sensitive calls fail silently in
a real browser (`segments.add`, `getView`, `setZoom`), leaving dead lanes
with no visible error — and that can't be debugged without browser
automation. The deterministic fallback won: hand-rolled canvas lanes
(proven ~1 ms redraws at 1200+ segments) with a zoomable waveform view
(native scroll), an overview bar with a draggable viewport box,
click-to-seek, hover tooltips and read-only segments colored by type
(speech blue, filler orange, music purple, highlight yellow, AI pink).

Custom player bar (play/pause, frame step, 0.5–2× speed, `HH:MM:SS:FF`
timecode, volume, fullscreen) plus Original / Cut-preview (real-time
skip, cut-time readout) / Rendered modes. Shortcuts: Space, J/K/L,
arrows (frame), Shift+arrows (1 s), +/− zoom, Ctrl+wheel zoom.

Audio: the video element stays muted; each lane plays its own
`/preview-audio` track in a synced `<audio>` element (mic boosted by
default, mute/solo per lane, drift > 50 ms resyncs). Manual editing
(drag/toggle/split/undo) is removed — render always uses the last
analysis timeline. The AI chat lives under the sidebar as PRE.AI and
needs nothing but Ollama; everything else works with Ollama off.

### Preview proxies (no more stutter)

Large sources are never played directly for **audio**. After a file is
added, `POST /proxy` builds once into `workspace/previews/<stem>/`:
per-track audio (`trackN.ogg` opus 96k, AAC fallback) — a cheap job that
finishes in seconds. The player reads those proxies: drift < 0.04 s does
nothing, 0.04–0.3 s nudges `playbackRate` 0.97/1.03, only > 0.3 s
hard-seeks; hard sync on play/pause/seek/buffering, playback starts after
all tracks `canplay`. `GET /proxy-audio` and `/proxy/{name}` (status) are
Range-capable (206). Proxy build failure falls back to direct files.

The **video** proxy (a 720p H.264 re-encode of the whole source) is
OFF by default (`PREVIEW_VIDEO_PROXY`). Re-encoding a multi-GB file
takes minutes and competes with analysis for CPU — that was the
"preparing preview 67%" stall, where two audio tracks were done and the
third step (video) ground on with a mis-read progress counter. With it
off, the `<video>` streams the original file directly and the proxy job
ends as soon as audio is ready. Turn it on under **Settings → Motor →
"Önizleme videosu (720p proxy)"** for huge/4K sources where a lighter
decode helps playback: ffmpeg then runs at below-normal priority and
reports real progress (ffmpeg's `out_time_ms` field is actually
microseconds, so it is divided by `duration * 1e6`).

### One heavy job at a time

Analysis (silence scan + optional Whisper), rendering (ffmpeg) and
standalone transcription (Whisper) share one heavy slot; running them
together starves CPU/RAM and can kill the server. Waiting jobs report
`stage: "queued"` — and since jobs name the slot holder, the UI shows
*what* they wait for (`blocked_by: {job_id, kind}`), e.g. "sırada ·
önizleme". Preview proxies run OUTSIDE the slot (thread-capped ffmpeg)
so starting an analysis never waits on preview generation.

- **Single heavy slot.** Only one render/transcribe computes at a time. The
  waiting job reports `stage: "queued"` until the slot frees, then continues
  with live progress.
- **Single-flight transcription.** Identical requests (same file, model,
  language and audio track) do not start a second Whisper — the new request
  joins the running job and returns its `job_id` with `"deduped": true`.
- **Job cleanup.** Finished/failed jobs are dropped from memory after an hour.

`PUT /settings` accepts any subset of `{threshold_db, min_silence,
padding_pre, padding_post, whisper_model, encoder, quality, output_audio,
preset, max_upload_gb}` (validated ranges; unknown keys
rejected) and applies them live — no restart. Stored in
`workspace/settings.json`, so defaults in `config.py` stay committable.

## Multi-track / multi-channel audio

Gameplay + voice-chat recordings usually separate sources:

- **Multi-track** (e.g. OBS multi-track: track 1 = mic, track 2 = game+Discord):
  pick the reference track with `audio_track` (0-based). Detection runs on
  that track (`-map 0:a:<track>`), but rendering applies the same cuts to
  **all** tracks so nothing is lost and everything stays in sync.
- **Stereo-split** (mic on left, game on right): set `audio_channel` to `0`
  (left) or `1` (right). Detection first isolates the channel
  (`pan=mono|c0=c<channel>`); the render keeps the original stereo.

`POST /streams` (same `filename` body) returns each track's `channels`,
`codec`, `language`, and `title`, plus `suggested_mic` and
`suggested_mic_confidence`: the first 120 s of each track are scanned for a
speech-like on/off pattern (many silence transitions at a balanced ratio);
if nothing scores, it falls back to title, then to the last track of
2-track files. The web UI preselects it and marks it "(mic?)". Invalid
track/channel values are rejected with a 400 error naming the available
tracks.

`/transcribe` accepts JSON:

```json
{
  "filename": "<stored upload filename>",
  "model": "base",
  "language": null,
  "remove_fillers": false,
  "audio_track": 0
}
```

`language: null` enables auto-detection. Transcription runs as a background
job like rendering: `POST /transcribe` returns `{job_id}` immediately, then
poll `GET /jobs/{job_id}` — it reports per-chunk progress
(`stage: "transcribe"`, `done`/`total`) and, when done, the transcript under
`result`: `language`, `words` (with `start`/`end`/`prob`/`filler`), `speech`
intervals (Silero VAD + word envelopes, music subtracted), `music` intervals
(background music is not treated as speech), `silence` intervals, `fillers`,
`filler_ratio`, and `cache_hit`. Whisper inference runs in 60 s chunks so
long files report live progress instead of hanging silently. With
`remove_fillers: true` a `filler_intervals` list is added
(TR/EN filler-word lists). Results are cached under `.precutter/` by file
hash, so repeat calls are instant. Requires `faster-whisper` + `torch`
(see `requirements.txt`); the Silero VAD model downloads on first use.
Whisper runs on the GPU when CTranslate2 sees one (`float16`), otherwise on
CPU (`int8`); `GET /doctor` reports the chosen device and GPU name.

## Tests

```bash
pytest
```

## Project layout

```
precutter/
  __init__.py
  config.py     # defaults and paths
  media.py      # ffmpeg/ffprobe checks and probing
  silence.py    # silencedetect parsing
  segments.py   # keep-segment construction and summary
  transcribe.py # whisper + Silero VAD + music/filler layers
  render.py     # trim/atrim + concat rendering
  app.py        # FastAPI application
  static/       # web UI
tests/
  test_segments.py
  test_transcribe.py
  test_limits.py
  test_audio.py
```

## Notes

- Uploads and outputs are stored under `workspace/uploads` and
  `workspace/outputs` (created automatically).
- Limits: max upload **4 GiB**, max video length **4 h** (`config.py`:
  `MAX_UPLOAD_BYTES`, `MAX_VIDEO_DURATION`). Oversized uploads get HTTP 413
  and partial files are deleted. `/health` reports the active limits.
- The web UI (TR/EN toggle in the header) shows upload progress (%, MB, speed),
  file info (name, size, duration), step indicator (upload → analyze → export),
  and a local video preview.
- Render cuts each kept segment to a `.mkv` intermediate (video + all audio
  tracks as PCM, so joins stay sample-accurate), joins them with the concat
  demuxer, then does one final pass: video copied, each audio track encoded
  to AAC once with source language/title metadata. NVIDIA GPUs use NVENC
  (`h264_nvenc`) automatically, otherwise libx264; the active encoder is
  reported by `/health`.
- Output video: H.264 (`libx264`, `veryfast`, CRF 20) with AAC 192k audio.

## License

PreCutter is released under the [MIT License](LICENSE).
Copyright 2026 Ekoo (EKOKAYGZ). Third-party notices are in [NOTICE](NOTICE).
