/* PreCutter view-only player (canvas lanes + overview, no editing).
 *
 * - Custom player bar: play/pause, frame step, speed, HH:MM:SS:FF, volume, fullscreen.
 * - Per-track lanes: zoomable waveform canvas (native scroll) + overview bar
 *   with a draggable viewport box. Read-only segments colored by type.
 * - Video is always muted; per-track <audio> elements stay synced
 *   (drift > 50ms -> resync, status line per lane). Mic lane boosted.
 * - Modes: original / cut (real-time skip, cut-time readout) / rendered.
 * No DOM edits to keep-segments exist anywhere in this file by design.
 */
const $ = (id) => document.getElementById(id);

const COLORS = {
  bg: "#121416",
  grid: "#2a2f34",
  text: "#8b9197",
  keep: "#3b82f6",
  filler: "#e8734a",
  music: "#a855f7",
  highlight: "#eab308",
  ai: "#f472b6",
  wave: "#4fb8a6",
  playhead: "#c9f05b",
};

const PPS_LEVELS = [4, 8, 16, 32, 64, 128, 256];
const ZOOM_H = 36;
const OV_H = 28;
const DRIFT_TOL = 0.05;
const MIC_BOOST = 1.0;
const GAME_LEVEL = 0.55;

const S = {
  video: null,
  filename: null,
  originalSrc: null,
  renderedUrl: null,
  duration: 0,
  fps: 30,
  keep: [], // [[s,e]]
  cuts: [], // [{start,end,reason}]
  music: [],
  speech: [], // [[s,e]] konuşma aralıkları (etiketler doğru olsun diye)
  highlights: [],
  mode: "original",
  lanes: [], // {track,muted,solo,base,audio,ready,peaks,els...}
  micTrack: 0,
  masterVol: 1,
  zoomIdx: 3,
  rafId: null,
  lastFrame: -1,
  tip: null,
  // Proxy state: 'idle' | 'working' | 'ready' | 'failed'.
  proxyState: "idle",
  proxyAudio: {}, // track -> url
  proxyVideo: null,
  pendingPlay: false,
};

function fmtTC(t) {
  t = Math.max(0, t || 0);
  const fps = S.fps > 0 ? S.fps : 30;
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = Math.floor(t % 60);
  const f = Math.floor(((t % 1) + 1e-6) * fps);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(h)}:${p(m)}:${p(s)}:${p(f)}`;
}

function fmtT(t) {
  t = Math.max(0, t || 0);
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/* Time span of the timeline: analysis duration, else the video's own.
 * Everything scroll-related uses this so the lanes can be panned even
 * before an analysis exists. */
function span() {
  if (S.duration > 0) return S.duration;
  const d = S.video ? S.video.duration : 0;
  return Number.isFinite(d) && d > 0 ? d : 0;
}

/* ---------- keep/cut math ---------- */
function sortedKeep() {
  return [...S.keep].sort((a, b) => a[0] - b[0]);
}

function gaps() {
  const out = [];
  let cursor = 0;
  for (const [s, e] of sortedKeep()) {
    if (s > cursor + 1e-9) out.push([cursor, s]);
    cursor = Math.max(cursor, e);
  }
  if (span() - cursor > 1e-9) out.push([cursor, span()]);
  return out;
}

function cutTime(t) {
  let cut = 0;
  for (const [s, e] of gaps()) {
    if (t >= e) cut += e - s;
    else if (t > s) { cut += t - s; break; }
    else break;
  }
  return Math.max(0, t - cut);
}

function nextKeepStart(t) {
  for (const [s, e] of sortedKeep()) {
    if (e > t + 1e-6) return Math.max(s, t);
  }
  return null;
}

/* Reason at time t for tooltips.
 * Cuts keep their own reason (filler/ai/silence). Kept ranges report what
 * actually covers t — speech, music, or plain "kept" — and any highlight
 * is appended instead of hiding the base reason. */
function inSpans(list, t) {
  for (const iv of list || []) {
    const s = Array.isArray(iv) ? iv[0] : (iv.start != null ? iv.start : iv.s);
    const e = Array.isArray(iv) ? iv[1] : (iv.end != null ? iv.end : iv.e);
    if (s == null || e == null) continue;
    if (t >= s && t < e) return true;
  }
  return false;
}

function segReason(t) {
  for (const c of S.cuts) {
    if (t >= c.start && t < c.end && (c.reason === "filler" || c.reason === "ai")) {
      return { kind: "cut", s: c.start, e: c.end, reason: c.reason };
    }
  }
  const hl = S.highlights.find((h) => t >= h.start && t < h.end) || null;
  for (const [s, e] of sortedKeep()) {
    if (t >= s && t < e) {
      const parts = [];
      if (inSpans(S.speech, t)) parts.push("speech");
      else if (inSpans(S.music, t)) parts.push("music");
      else parts.push("kept");
      if (hl) parts.push(`highlight ${hl.score}`);
      return { kind: "keep", s, e, reason: parts.join(" + ") };
    }
    if (s > t) break;
  }
  let cursor = 0;
  for (const [s, e] of sortedKeep()) {
    if (t >= cursor && t < s) return { kind: "cut", s: cursor, e: s, reason: "silence" };
    cursor = Math.max(cursor, e);
  }
  return { kind: "cut", s: cursor, e: span(), reason: "silence" };
}

/* ---------- audio lanes ---------- */
function laneGain(lane) {
  if (lane.muted) return 0;
  const anySolo = S.lanes.some((l) => l.solo);
  if (anySolo && !lane.solo) return 0;
  return S.masterVol * lane.base;
}

function applyGains() {
  for (const lane of S.lanes) {
    if (!lane.audio) continue;
    lane.audio.volume = Math.max(0, Math.min(1, laneGain(lane)));
    if (S.video) lane.audio.playbackRate = S.video.playbackRate;
  }
}

function laneStatus(lane, text) {
  if (lane.statusEl) lane.statusEl.textContent = text;
}

function attachAudio(lane) {
  if (lane.audio || !S.filename) return;
  // Proxy hazır değilse bekle (istek anında yarım dosya sunulmaz);
  // proxy başarısızsa tam dosyaya düş.
  const url = S.proxyAudio[lane.track]
    || (S.proxyState === "failed"
      ? `/preview-audio/${encodeURIComponent(S.filename)}?track=${lane.track}`
      : null);
  if (!url) {
    laneStatus(lane, "ses hazırlanıyor…");
    return;
  }
  const a = new Audio();
  a.preload = "auto";
  laneStatus(lane, "ses hazırlanıyor…");
  a.addEventListener("canplay", () => {
    lane.ready = true;
    laneStatus(lane, "");
    applyGains();
    if (S.pendingPlay) tryStartPending();
  });
  a.addEventListener("error", () => {
    lane.ready = false;
    if (!S.proxyAudio[lane.track] && S.proxyState !== "failed") {
      laneStatus(lane, "ses hazırlanıyor…");
    } else {
      laneStatus(lane, "ses yüklenemedi");
    }
  });
  a.src = url;
  lane.audio = a;
  applyGains();
}

function allAudioReady() {
  const act = S.lanes.filter((l) => l.audio && l.audio.src);
  return act.length > 0 && act.every((l) => l.ready);
}

/* Nudge sync: normal oynatmada currentTime'a ASLA dokunma. */
function nudgeSync() {
  if (!S.video || S.video.paused || S.mode === "rendered") return;
  const t = S.video.currentTime;
  const base = S.video.playbackRate || 1;
  for (const lane of S.lanes) {
    const a = lane.audio;
    if (!a || !a.src || a.paused || !lane.ready) continue;
    const drift = a.currentTime - t;
    const ad = Math.abs(drift);
    if (ad < 0.04) {
      if (a.playbackRate !== base) a.playbackRate = base;
    } else if (ad <= 0.3) {
      a.playbackRate = base * (drift > 0 ? 0.97 : 1.03);
    } else {
      try { a.currentTime = t; } catch (e) { /* ignore */ }
    }
  }
}

function syncAudios(force) {
  if (!S.video || S.mode === "rendered") return;
  const t = S.video.currentTime;
  for (const lane of S.lanes) {
    const a = lane.audio;
    if (!a || !a.src) continue;
    if (force || Math.abs(a.currentTime - t) > DRIFT_TOL) {
      try { a.currentTime = Math.min(Math.max(t, 0), a.duration || t); } catch (e) { /* ignore */ }
    }
  }
}

function audiosPlay() {
  if (S.mode === "rendered") return;
  syncAudios(true);
  for (const lane of S.lanes) {
    if (lane.audio && lane.audio.src) lane.audio.play().catch(() => {});
  }
}

function audiosPause() {
  for (const lane of S.lanes) {
    if (lane.audio) { try { lane.audio.pause(); } catch (e) { /* ignore */ } }
  }
}

/* ---------- lane DOM ---------- */
function laneLabel(tr) {
  const parts = [`Track ${tr.track + 1}`, `${tr.channels}ch`];
  if (tr.title) parts.push(tr.title);
  if (tr.codec) parts.push(tr.codec);
  return parts.join(" · ");
}

function buildLanes(tracks, micTrack) {
  const box = $("lanes");
  if (!box) return;
  box.innerHTML = "";
  S.lanes = [];
  S.micTrack = micTrack || 0;
  for (const tr of (tracks || []).slice(0, 2)) {
    const wrap = document.createElement("div");
    wrap.className = "lane";
    const head = document.createElement("div");
    head.className = "lane-head";
    const name = document.createElement("span");
    name.className = "lane-name mono";
    name.textContent = laneLabel(tr) + (tr.track === S.micTrack ? " (mic)" : "");
    const status = document.createElement("span");
    status.className = "mono lane-status";
    const mute = document.createElement("button");
    mute.className = "lane-btn";
    mute.type = "button";
    mute.textContent = "M";
    mute.title = "mute";
    const solo = document.createElement("button");
    solo.className = "lane-btn";
    solo.type = "button";
    solo.textContent = "S";
    solo.title = "solo";
    const vol = document.createElement("input");
    vol.className = "lane-vol";
    vol.type = "range";
    vol.min = "0";
    vol.max = "1";
    vol.step = "0.05";
    vol.value = String(tr.track === S.micTrack ? MIC_BOOST : GAME_LEVEL);
    vol.title = "track volume";
    head.appendChild(name);
    head.appendChild(status);
    head.appendChild(vol);
    head.appendChild(mute);
    head.appendChild(solo);
    const scroll = document.createElement("div");
    scroll.className = "zoom-scroll";
    const track = document.createElement("div");
    track.className = "zoom-track"; // kaydırma genişliği: süre * pps
    const zoom = document.createElement("canvas");
    zoom.className = "zoom-cv";
    scroll.appendChild(track);
    scroll.appendChild(zoom);
    wrap.appendChild(head);
    wrap.appendChild(scroll);
    box.appendChild(wrap);
    const lane = {
      track: tr.track, muted: false, solo: false,
      base: tr.track === S.micTrack ? MIC_BOOST : GAME_LEVEL,
      audio: null, ready: false, peaks: null,
      scrollEl: scroll, zoomCv: zoom, trackEl: track, statusEl: status,
      muteBtn: mute, soloBtn: solo, scrollRaf: null,
    };
    mute.addEventListener("click", () => {
      lane.muted = !lane.muted;
      mute.classList.toggle("active", lane.muted);
      applyGains();
    });
    solo.addEventListener("click", () => {
      lane.solo = !lane.solo;
      solo.classList.toggle("active", lane.solo);
      applyGains();
    });
    vol.addEventListener("input", () => {
      lane.base = Number(vol.value);
      applyGains();
    });
    scroll.addEventListener("scroll", () => {
      syncLaneScroll(lane);
      if (lane.scrollRaf == null) {
        lane.scrollRaf = requestAnimationFrame(() => {
          lane.scrollRaf = null;
          drawLane(lane);
          drawOverviewAll();
        });
      }
    });
    zoom.addEventListener("click", (e) => {
      if (!S.video || !span()) return;
      const r = zoom.getBoundingClientRect();
      const t = (scroll.scrollLeft + (e.clientX - r.left)) / pps();
      S.video.currentTime = Math.min(Math.max(t, 0), span() || Infinity);
      syncAudios(true);
    });
    zoom.addEventListener("mousemove", (e) => {
      if (!span() || !S.tip) return;
      const r = zoom.getBoundingClientRect();
      const t = (scroll.scrollLeft + (e.clientX - r.left)) / pps();
      const seg = segReason(Math.min(Math.max(t, 0), span() || Infinity));
      S.tip.textContent = `${fmtTC(seg.s)} → ${fmtTC(seg.e)} · ${seg.reason}`;
      S.tip.hidden = false;
    });
    zoom.addEventListener("mouseleave", () => { if (S.tip) S.tip.hidden = true; });
    attachAudio(lane);
    fetchPeaks(lane);
    S.lanes.push(lane);
  }
  applyGains();
  layoutAll();
}

/* All lanes share one scroll position (single timeline). */
let syncingScroll = false;
function syncLaneScroll(from) {
  if (syncingScroll) return;
  syncingScroll = true;
  try {
    for (const lane of S.lanes) {
      if (lane !== from) lane.scrollEl.scrollLeft = from.scrollEl.scrollLeft;
    }
  } finally {
    syncingScroll = false;
  }
}

async function fetchPeaks(lane) {
  if (!S.filename) return;
  try {
    const r = await fetch(
      `/waveform/${encodeURIComponent(S.filename)}?track=${lane.track}&peaks=4000`);
    if (!r.ok) throw new Error("peaks failed");
    const data = await r.json();
    if (Array.isArray(data.peaks) && data.peaks.length) {
      lane.peaks = data.peaks;
      drawLane(lane);
      drawOverviewAll();
    }
  } catch (e) { /* waveform stays empty, segments still draw */ }
}

/* ---------- canvas drawing ---------- */
function pps() {
  return PPS_LEVELS[S.zoomIdx];
}

function setupCanvas(cv, cssW, cssH) {
  const dpr = window.devicePixelRatio || 1;
  cv.style.width = `${Math.ceil(cssW)}px`;
  cv.style.height = `${cssH}px`;
  cv.width = Math.max(1, Math.round(cssW * dpr));
  cv.height = Math.max(1, Math.round(cssH * dpr));
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}

function rulerStep() {
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  for (const st of steps) {
    if (st * pps() >= 70) return st;
  }
  return 900;
}

function drawLane(lane) {
  const scroll = lane.scrollEl;
  const cssW = Math.max(scroll.clientWidth || 600, 50);
  // Scroll'un çalışması için içerik süre*pps kadar geniş olmalı; canvas ise
  // viewport'a sabitlenir. Yoksa scrollLeft her zaman 0 kalır ve zaman
  // ekseni başta donup kalır (işaretler yanlış yerde görünür).
  if (lane.trackEl) {
    const tw = `${Math.max(0, Math.ceil(span() * pps()))}px`;
    if (lane.trackEl.style.width !== tw) lane.trackEl.style.width = tw;
  }
  lane.zoomCv.style.transform = `translateX(${scroll.scrollLeft}px)`;
  const ctx = setupCanvas(lane.zoomCv, cssW, ZOOM_H);
  const p = pps();
  const t0 = scroll.scrollLeft / p;
  const t1 = t0 + cssW / p;
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, cssW, ZOOM_H);
  if (!S.duration) return;
  // Keep base + colored cut overlays.
  ctx.fillStyle = COLORS.keep;
  for (const [s, e] of sortedKeep()) {
    if (e < t0 || s > t1) continue;
    ctx.fillRect(Math.max(0, (s - t0) * p), 0, (e - s) * p, ZOOM_H);
  }
  const overlay = (list, color) => {
    ctx.fillStyle = color;
    for (const c of list) {
      if (c.end < t0 || c.start > t1) continue;
      ctx.fillRect(Math.max(0, (c.start - t0) * p), 0, (c.end - c.start) * p, ZOOM_H);
    }
  };
  overlay(S.cuts.filter((c) => c.reason === "filler"), COLORS.filler);
  overlay(S.cuts.filter((c) => c.reason === "ai"), COLORS.ai);
  overlay(S.highlights.map((h) => ({ start: h.start, end: h.end })), "rgba(234,179,8,0.55)");
  // Music strip on top.
  ctx.fillStyle = "rgba(168,85,247,0.85)";
  for (const m of S.music) {
    const s = m[0] != null ? m[0] : m.s;
    const e = m[1] != null ? m[1] : m.e;
    if (e < t0 || s > t1) continue;
    ctx.fillRect(Math.max(0, (s - t0) * p), 0, (e - s) * p, 7);
  }
  // Speech strip at the bottom: nerede konuştuğunu gösterir.
  ctx.fillStyle = "rgba(229,231,235,0.8)";
  for (const iv of S.speech) {
    const s = Array.isArray(iv) ? iv[0] : iv.start;
    const e = Array.isArray(iv) ? iv[1] : iv.end;
    if (s == null || e == null || e < t0 || s > t1) continue;
    ctx.fillRect(Math.max(0, (s - t0) * p), ZOOM_H - 4,
                 Math.max(1, (e - s) * p), 4);
  }
  // Waveform.
  const dur = span();
  if (lane.peaks && lane.peaks.length && dur > 0) {
    const n = lane.peaks.length;
    ctx.fillStyle = "rgba(79,184,166,0.9)";
    const mid = ZOOM_H / 2;
    const amp = ZOOM_H / 2 - 4;
    for (let x = 0; x < cssW; x++) {
      const t = t0 + x / p;
      const v = lane.peaks[Math.min(n - 1, Math.max(0, Math.floor((t / dur) * n)))] || 0;
      const h = Math.max(1, v * amp);
      ctx.fillRect(x, mid - h, 1, h * 2);
    }
  }
  // Ruler.
  const step = rulerStep();
  ctx.fillStyle = COLORS.text;
  ctx.font = "10px 'JetBrains Mono', monospace";
  const first = Math.ceil(t0 / step) * step;
  for (let t = first; t <= t1; t += step) {
    const x = Math.round((t - t0) * p) + 0.5;
    ctx.fillRect(x, 0, 1, 5);
    ctx.fillText(fmtT(t), x + 3, 12);
  }
  // Playhead.
  if (S.video) {
    const x = (S.video.currentTime - t0) * p;
    if (x >= 0 && x <= cssW) {
      ctx.fillStyle = COLORS.playhead;
      ctx.fillRect(x - 1, 0, 2, ZOOM_H);
    }
  }
}

/* Single shared overview for all lanes (one timeline, one viewport). */
function ovCanvas() {
  return $("ovAll");
}

function drawOverviewAll() {
  const ov = ovCanvas();
  if (!ov) return;
  const cssW = Math.max(ov.clientWidth || ov.parentElement.clientWidth || 600, 50);
  const ctx = setupCanvas(ov, cssW, OV_H);
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, cssW, OV_H);
  const dur = span();
  if (!dur) return;
  const X = (t) => (t / dur) * cssW;
  ctx.fillStyle = COLORS.keep;
  for (const [s, e] of sortedKeep()) {
    ctx.fillRect(X(s), 6, Math.max(1, X(e) - X(s)), OV_H - 12);
  }
  const peaks = (S.lanes.find((l) => l.peaks && l.peaks.length) || {}).peaks;
  if (peaks) {
    const n = peaks.length;
    ctx.fillStyle = "rgba(79,184,166,0.55)";
    const mid = OV_H / 2;
    for (let x = 0; x < cssW; x += 2) {
      const v = peaks[Math.min(n - 1, Math.floor((x / cssW) * n))] || 0;
      const h = Math.max(1, v * (OV_H / 2 - 3));
      ctx.fillRect(x, mid - h, 1, h * 2);
    }
  }
  // Viewport box (all lanes share scroll).
  const first = S.lanes[0];
  if (first) {
    const p = pps();
    const vx = (first.scrollEl.scrollLeft / p / dur) * cssW;
    const vw = (first.scrollEl.clientWidth / p / dur) * cssW;
    ctx.strokeStyle = "#e5e7eb";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(vx + 0.5, 1.5, Math.max(4, vw), OV_H - 3);
  }
  // Playhead.
  if (S.video) {
    ctx.fillStyle = COLORS.playhead;
    ctx.fillRect(X(S.video.currentTime) - 1, 0, 2, OV_H);
  }
}

function redrawAll() {
  for (const lane of S.lanes) {
    drawLane(lane);
  }
  drawOverviewAll();
}

function layoutAll() {
  redrawAll();
}

function wireOverviewAll() {
  const ov = ovCanvas();
  if (!ov || ov._wired) return;
  ov._wired = true;
  let drag = null; // {mode:'view'|'seek'}
  const pos = (e) => {
    const r = ov.getBoundingClientRect();
    return { x: e.clientX - r.left, w: r.width };
  };
  const geom = (w) => {
    const first = S.lanes[0];
    const p = pps();
    const totalPx = span() * p;
    const vw = first ? first.scrollEl.clientWidth : w;
    const sl = first ? first.scrollEl.scrollLeft : 0;
    return { first, totalPx, vw, sl };
  };
  const setScroll = (px) => {
    const { first, totalPx, vw } = geom(0);
    if (!first) return;
    first.scrollEl.scrollLeft = Math.min(
      Math.max(px, 0), Math.max(0, totalPx - vw));
  };
  ov.addEventListener("mousedown", (e) => {
    if (!span() || !S.lanes.length) return;
    const { x, w } = pos(e);
    const { sl, vw } = geom(w);
    const p = pps();
    const vx = (sl / p / span()) * w;
    const vwid = (vw / p / span()) * w;
    const t = (x / w) * span();
    if (x >= vx && x <= vx + vwid) {
      drag = { mode: "view", off: x - vx };
    } else {
      drag = { mode: "seek" };
      if (S.video) {
        S.video.currentTime = Math.min(Math.max(t, 0), span() || Infinity);
        syncAudios(true);
      }
      centerOn(t);
    }
    e.preventDefault();
  });
  ov.addEventListener("mousemove", (e) => {
    if (!drag || !span() || !S.lanes.length) return;
    const { x, w } = pos(e);
    const { totalPx, vw } = geom(w);
    if (drag.mode === "view") {
      const frac = (x - drag.off) / w;
      setScroll(frac * totalPx);
    } else if (S.video) {
      const t = (x / w) * span();
      S.video.currentTime = Math.min(Math.max(t, 0), span() || Infinity);
      syncAudios(true);
    }
  });
  window.addEventListener("mouseup", () => { drag = null; });
}

function centerOn(t, onlyLane) {
  const lanes = onlyLane ? [onlyLane] : S.lanes;
  for (const lane of lanes) {
    const p = pps();
    const totalPx = span() * p;
    const vw = lane.scrollEl.clientWidth;
    lane.scrollEl.scrollLeft = Math.min(
      Math.max(t * p - vw / 2, 0), Math.max(0, totalPx - vw));
  }
}

function timeAtCursor(lane, clientX) {
  const r = lane.zoomCv.getBoundingClientRect();
  return (lane.scrollEl.scrollLeft + (clientX - r.left)) / pps();
}

function setZoomAll(idx, anchorT) {
  const ni = Math.max(0, Math.min(PPS_LEVELS.length - 1, idx));
  if (ni === S.zoomIdx) return;
  const t = anchorT != null ? anchorT
    : (S.video ? S.video.currentTime : span() / 2);
  S.zoomIdx = ni;
  const p = pps();
  for (const lane of S.lanes) {
    const totalPx = span() * p;
    const vw = lane.scrollEl.clientWidth;
    lane.scrollEl.scrollLeft = Math.min(
      Math.max(t * p - vw / 2, 0), Math.max(0, totalPx - vw));
  }
  redrawAll();
}

/* ---------- transport ---------- */
function updateTime() {
  const el = $("ppTime");
  if (el && S.video) {
    el.textContent = fmtTC(S.mode === "cut" ? cutTime(S.video.currentTime) : S.video.currentTime);
  }
  const scrub = $("ppScrub");
  if (scrub && S.video && S.duration > 0 && document.activeElement !== scrub) {
    scrub.value = String(Math.round(
      (S.video.currentTime / S.duration) * 1000));
  }
  const btn = $("ppPlay");
  if (btn && S.video) btn.textContent = S.video.paused ? "▶" : "⏸";
}

function tick() {
  S.rafId = null;
  if (!S.video) return;
  const t = S.video.currentTime;
  if (S.mode === "cut" && !S.video.paused && S.keep.length) {
    const nx = nextKeepStart(t - 1e-4);
    const inKeep = S.keep.some(([s, e]) => t >= s - 1e-4 && t < e);
    if (!inKeep && nx != null && nx < (S.duration || Infinity)) {
      S.video.currentTime = nx;
      syncAudios(true);
    }
  }
  const frame = Math.floor(t * 30);
  if (frame !== S.lastFrame) {
    S.lastFrame = frame;
    nudgeSync();
    redrawAll();
  }
  updateTime();
  if (!S.video.paused && !S.video.ended) {
    S.rafId = requestAnimationFrame(tick);
  }
}

function tryStartPending() {
  if (!S.pendingPlay) return;
  if (!allAudioReady()) return;
  S.pendingPlay = false;
  startVideo();
}

function play() {
  if (!S.video || !S.video.src) return;
  // Tüm izler canplay demeden başlama (kesik ses yok).
  if (S.mode !== "rendered" && S.lanes.some((l) => l.audio && l.audio.src) && !allAudioReady()) {
    S.pendingPlay = true;
    for (const lane of S.lanes) {
      if (lane.audio && lane.audio.src && !lane.ready) laneStatus(lane, "ses hazırlanıyor…");
    }
    return;
  }
  startVideo();
}

function startVideo() {
  if (S.mode === "rendered") {
    S.video.muted = false;
    audiosPause();
  } else {
    S.video.muted = true;
    audiosPlay();
  }
  S.video.play().catch(() => {});
  if (S.rafId == null) S.rafId = requestAnimationFrame(tick);
}

function pause() {
  if (!S.video) return;
  S.video.pause();
  audiosPause();
  updateTime();
}

function toggle() {
  if (!S.video) return;
  if (S.video.paused) play();
  else pause();
}

function stepFrame(dir) {
  if (!S.video) return;
  pause();
  const fps = S.fps > 0 ? S.fps : 30;
  S.video.currentTime = Math.min(
    Math.max(S.video.currentTime + (dir * 1) / fps, 0),
    S.duration || S.video.duration || 0);
  syncAudios(true);
  redrawAll();
  updateTime();
}

function seekBy(sec) {
  if (!S.video) return;
  S.video.currentTime = Math.min(
    Math.max(S.video.currentTime + sec, 0), S.duration || S.video.duration || 0);
  syncAudios(true);
  redrawAll();
  updateTime();
}

function setSpeed(v) {
  if (!S.video) return;
  S.video.playbackRate = v;
  applyGains();
}

function setMode(mode, silent) {
  S.mode = mode;
  for (const m of ["original", "cut", "rendered"]) {
    const btn = $(`mode${m[0].toUpperCase() + m.slice(1)}`);
    if (btn) btn.classList.toggle("active", m === mode);
  }
  if (!S.video) return;
  const wasPlaying = !S.video.paused;
  pause();
  if (mode === "rendered" && S.renderedUrl) {
    S.video.src = S.renderedUrl;
    S.video.muted = false;
  } else {
    if (S.originalSrc && S.video.src !== S.originalSrc) S.video.src = S.originalSrc;
    S.video.muted = true;
  }
  if (wasPlaying && !silent) play();
  else updateTime();
}

/* ---------- bridge (app.js talks to this) ---------- */
function loadAnalysis(data) {
  S.duration = data.duration || 0;
  S.fps = data.fps > 0 ? data.fps : 30;
  S.keep = (data.segments || []).map(([s, e]) => [s, e]);
  S.cuts = data.cuts || [];
  S.music = data.music || [];
  S.speech = data.speech || [];
  S.highlights = data.highlights || [];
  S.filename = data.filename || S.filename;
  S.lastFrame = -1;
  if (data.tracks && data.tracks.length) {
    buildLanes(data.tracks, data.micIndex);
  } else if (!S.lanes.length) {
    buildLanes([{ track: 0, channels: 2, codec: "", title: "" }], 0);
  } else {
    for (const lane of S.lanes) {
      attachAudio(lane);
      fetchPeaks(lane);
    }
  }
  applyGains();
  redrawAll();
  updateTime();
}

function setAudioTracks(tracks, micIndex, filename) {
  if (filename) S.filename = filename;
  buildLanes(tracks || [], micIndex || 0);
}

function setRenderedUrl(url) {
  S.renderedUrl = url;
  const btn = $("modeRendered");
  if (btn) btn.disabled = !url;
}

function setProxies(payload) {
  // payload: {audio: {track: url}, video: url|null, failed?: bool}
  S.proxyState = payload && payload.failed ? "failed" : "ready";
  S.proxyAudio = (payload && payload.audio) || {};
  const vurl = payload && payload.video;
  S.proxyVideo = vurl || null;
  for (const lane of S.lanes) {
    // Eski src'yi bırak: yeni proxy'ye geç (yüklenemediyse fallback dener).
    lane.audio = null;
    lane.ready = false;
    attachAudio(lane);
  }
  if (vurl && S.mode !== "rendered" && S.video) {
    const t = S.video.currentTime || 0;
    const paused = S.video.paused;
    S.video.src = vurl;
    S.originalSrc = vurl;
    const restore = () => {
      try { S.video.currentTime = Math.min(t, S.video.duration || t); } catch (e) { /* ignore */ }
      if (!paused) play();
    };
    if (S.video.readyState >= 1) restore();
    else S.video.addEventListener("loadedmetadata", restore, { once: true });
  }
  if (S.pendingPlay) tryStartPending();
}

function proxyFailed() {
  S.proxyState = "failed";
  S.proxyAudio = {};
  for (const lane of S.lanes) {
    lane.audio = null;
    lane.ready = false;
    attachAudio(lane); // tam dosyaya düşer
  }
  if (S.pendingPlay) tryStartPending();
}

/* Proxy işi sürerken biten parçayı hemen tak (ses için video bitimini bekleme). */
function noteProxyProgress(status) {
  if (!status || !S.filename) return;
  let changed = false;
  for (const [track, file] of Object.entries(status.audio || {})) {
    if (file && !S.proxyAudio[track]) {
      S.proxyAudio[track] = `/proxy-audio/${encodeURIComponent(S.filename)}?track=${track}`;
      changed = true;
    }
  }
  if (changed) {
    if (S.proxyState === "idle") S.proxyState = "working";
    for (const lane of S.lanes) {
      if (!lane.audio) attachAudio(lane);
    }
    if (S.pendingPlay) tryStartPending();
  }
  if (status.video && !S.proxyVideo) {
    setProxies({
      audio: S.proxyAudio,
      video: `/proxy-video/${encodeURIComponent(S.filename)}`,
    });
  }
}

function resetPlayer() {
  if (S.rafId != null) {
    cancelAnimationFrame(S.rafId);
    S.rafId = null;
  }
  audiosPause();
  S.lanes = [];
  S.keep = [];
  S.cuts = [];
  S.music = [];
  S.speech = [];
  S.highlights = [];
  S.duration = 0;
  S.filename = null;
  S.originalSrc = null;
  S.renderedUrl = null;
  S.lastFrame = -1;
  S.proxyState = "idle";
  S.proxyAudio = {};
  S.proxyVideo = null;
  S.pendingPlay = false;
  const box = $("lanes");
  if (box) box.innerHTML = "";
  const btn = $("modeRendered");
  if (btn) btn.disabled = true;
  setModeSilent("original");
}

function setModeSilent(mode) {
  S.mode = mode;
  for (const m of ["original", "cut", "rendered"]) {
    const btn = $(`mode${m[0].toUpperCase() + m.slice(1)}`);
    if (btn) btn.classList.toggle("active", m === mode);
  }
}

/* ---------- boot ---------- */
function boot() {
  S.video = $("previewVideo");
  S.tip = $("tlTip");
  if (!S.video) return;
  S.video.addEventListener("play", () => {
    if (S.mode !== "rendered") audiosPlay();
    if (S.rafId == null) S.rafId = requestAnimationFrame(tick);
    updateTime();
  });
  S.video.addEventListener("playing", () => {
    if (S.mode !== "rendered") audiosPlay();
  });
  S.video.addEventListener("pause", () => {
    S.pendingPlay = false;
    audiosPause();
    updateTime();
  });
  S.video.addEventListener("waiting", () => {
    // Video arabelleğe alırken sesi de durdur (geriden gelen ses yok).
    audiosPause();
  });
  S.video.addEventListener("seeked", () => {
    syncAudios(true);
    redrawAll();
    updateTime();
  });
  S.video.addEventListener("timeupdate", updateTime);
  S.video.addEventListener("loadedmetadata", () => {
    if (!S.originalSrc && S.video.src) S.originalSrc = S.video.src;
    updateTime();
  });
  $("ppPlay").addEventListener("click", toggle);
  $("ppScrub").addEventListener("input", (e) => {
    if (!S.video || !S.duration) return;
    S.video.currentTime = Math.min(
      Math.max((Number(e.target.value) / 1000) * S.duration, 0), S.duration);
    syncAudios(true);
  });
  $("ppFrameBack").addEventListener("click", () => stepFrame(-1));
  $("ppFrameFwd").addEventListener("click", () => stepFrame(1));
  $("ppSpeed").addEventListener("change", (e) => setSpeed(Number(e.target.value) || 1));
  $("ppVol").addEventListener("input", (e) => {
    S.masterVol = Number(e.target.value);
    applyGains();
  });
  $("ppFull").addEventListener("click", () => {
    const box = $("previewBox");
    if (!box) return;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else if (box.requestFullscreen) box.requestFullscreen().catch(() => {});
  });
  for (const m of ["original", "cut", "rendered"]) {
    const btn = $(`mode${m[0].toUpperCase() + m.slice(1)}`);
    if (btn) btn.addEventListener("click", () => setMode(m));
  }
  wireOverviewAll();
  document.addEventListener("keydown", (e) => {
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (!S.video || !S.video.src) return;
    const k = e.key;
    if (k === " ") { e.preventDefault(); toggle(); }
    else if (k === "j" || k === "J") { seekBy(-5); }
    else if (k === "k" || k === "K") { pause(); }
    else if (k === "l" || k === "L") {
      if (S.video.paused) play();
      else {
        const order = [0.5, 0.75, 1, 1.25, 1.5, 2];
        const i = order.indexOf(S.video.playbackRate);
        const nx = order[Math.min(order.length - 1, (i < 0 ? 2 : i) + 1)];
        S.video.playbackRate = nx;
        const sel = $("ppSpeed");
        if (sel) sel.value = String(nx);
        applyGains();
      }
    }
    else if (k === "ArrowLeft") { e.preventDefault(); e.shiftKey ? seekBy(-1) : stepFrame(-1); }
    else if (k === "ArrowRight") { e.preventDefault(); e.shiftKey ? seekBy(1) : stepFrame(1); }
    else if (k === "+" || k === "=") {
      e.preventDefault();
      setZoomAll(S.zoomIdx + 1, S.video.currentTime);
    }
    else if (k === "-" || k === "_") {
      e.preventDefault();
      setZoomAll(S.zoomIdx - 1, S.video.currentTime);
    }
  });
  document.addEventListener("wheel", (e) => {
    if (!e.ctrlKey || !S.lanes.length) return;
    e.preventDefault();
    const lane = S.lanes[0];
    const t = timeAtCursor(lane, e.clientX);
    setZoomAll(S.zoomIdx + (e.deltaY < 0 ? 1 : -1), t);
  }, { passive: false });
  window.addEventListener("resize", () => redrawAll());
  window.PrecutterPlayer = {
    loadAnalysis,
    setAudioTracks,
    setRenderedUrl,
    setProxies,
    proxyFailed,
    noteProxyProgress,
    reset: resetPlayer,
  };
  updateTime();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
