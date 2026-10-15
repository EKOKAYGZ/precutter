# PreCutter v0.1

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

Then open http://127.0.0.1:8000 in your browser.

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
| POST   | `/analyze`        | Detect silences and return segments  |
| POST   | `/streams`        | List audio tracks/channels of a file |
| GET    | `/projects`       | List uploaded project files          |
| GET    | `/media/{name}`   | Stream an upload for local preview   |
| POST   | `/transcribe`     | Whisper transcript (words, VAD, music, fillers) |
| POST   | `/render`         | Start a background render job        |
| GET    | `/jobs/{job_id}`  | Render progress / result             |
| GET    | `/preview-audio/{name}?track=N` | Extract one audio track for audition |
| GET    | `/download/{name}`| Download a rendered output           |

`/analyze` and `/render` accept JSON:

```json
{
  "filename": "<stored upload filename>",
  "threshold_db": -35,
  "min_silence": 0.6,
  "padding": 0.15,
  "audio_track": 0,
  "audio_channel": null
}
```

Errors are returned as JSON with a `detail` field.

`POST /render` returns `{job_id}` immediately and renders in a background
thread; poll `GET /jobs/{job_id}` for `{status, stage, done, total}` until
`status` is `done` (with `download_url` + `summary`) or `error`. This keeps
long renders from outliving the HTTP connection. `GET /preview-audio/{name}`
extracts one audio track as `.m4a` (cached under `workspace/previews/`) so
you can hear which track is the mic before analyzing.

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
`codec`, `language`, and `title` so clients can build a source picker. The
web UI shows an "Audio source" dropdown when a file has more than one track,
plus a Mix/Left/Right selector for stereo tracks. Invalid track/channel
values are rejected with a 400 error naming the available tracks.

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

`language: null` enables auto-detection. The response contains `language`,
`words` (with `start`/`end`/`prob`/`filler`), `speech` intervals (Silero VAD
+ word envelopes, music subtracted), `music` intervals (background music is
not treated as speech), `silence` intervals, `fillers`, `filler_ratio`, and
`cache_hit`. With `remove_fillers: true` a `filler_intervals` list is added
(TR/EN filler-word lists). Results are cached under `.precutter/` by file
hash, so repeat calls are instant. Requires `faster-whisper` + `torch`
(see `requirements.txt`); the Silero VAD model downloads on first use.

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
  file info (name, size, duration), step indicator (upload â†’ analyze â†’ export),
  and a local video preview.
- Render encodes each kept segment separately (fast+accurate seeking) and joins
  with the concat demuxer, so any segment count works and all audio tracks
  are preserved.
- Output video: H.264 (`libx264`, `veryfast`, CRF 20) with AAC 192k audio.
