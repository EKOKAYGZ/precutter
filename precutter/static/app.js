const els = {
  drop: document.getElementById("drop"),
  fileInput: document.getElementById("fileInput"),
  dropHint: document.getElementById("dropHint"),
  uploadProgress: document.getElementById("uploadProgress"),
  uploadPct: document.getElementById("uploadPct"),
  uploadSpeed: document.getElementById("uploadSpeed"),
  uploadFill: document.getElementById("uploadFill"),
  fileChip: document.getElementById("fileChip"),
  fileName: document.getElementById("fileName"),
  fileMeta: document.getElementById("fileMeta"),
  fileRemove: document.getElementById("fileRemove"),
  previewVideo: document.getElementById("previewVideo"),
  previewPlaceholder: document.getElementById("previewPlaceholder"),
  previewTag: document.getElementById("previewTag"),
  threshold: document.getElementById("threshold"),
  thresholdValue: document.getElementById("thresholdValue"),
  minSilence: document.getElementById("minSilence"),
  minSilenceValue: document.getElementById("minSilenceValue"),
  padding: document.getElementById("padding"),
  paddingValue: document.getElementById("paddingValue"),
  settingsSub: document.getElementById("settingsSub"),
  presetRow: document.getElementById("presetRow"),
  fillerSwitch: document.getElementById("fillerSwitch"),
  fillerInfo: document.getElementById("fillerInfo"),
  audioTrack: document.getElementById("audioTrack"),
  channelField: document.getElementById("channelField"),
  audioChannel: document.getElementById("audioChannel"),
  noAudioHelp: document.getElementById("noAudioHelp"),
  auditionBtn: document.getElementById("auditionBtn"),
  auditionStatus: document.getElementById("auditionStatus"),
  auditionAudio: document.getElementById("auditionAudio"),
  jsonBtn: document.getElementById("jsonBtn"),
  renderBtn: document.getElementById("renderBtn"),
  exportNote: document.getElementById("exportNote"),
  previewToggle: document.getElementById("previewToggle"),
  outputMeta: document.getElementById("outputMeta"),
  timeline: document.getElementById("timeline"),
  timelineEmpty: document.getElementById("timelineEmpty"),
  ruler: document.getElementById("ruler"),
  statTotal: document.getElementById("statTotal"),
  statKept: document.getElementById("statKept"),
  statCut: document.getElementById("statCut"),
  summaryLine: document.getElementById("summaryLine"),
  renderProgress: document.getElementById("renderProgress"),
  renderPct: document.getElementById("renderPct"),
  renderStage: document.getElementById("renderStage"),
  renderFill: document.getElementById("renderFill"),
  renderStatus: document.getElementById("renderStatus"),
  downloadLink: document.getElementById("downloadLink"),
  error: document.getElementById("error"),
  langTr: document.getElementById("langTr"),
  langEn: document.getElementById("langEn"),
};

/* ---------- i18n ---------- */
const STR = {
  tr: {
    localBadge: "yerel analiz · bulut yok",
    dropTitle: "Videoyu buraya bırak veya gözatmak için tıkla",
    dropHint: ".mp4 · .mkv · .mov · en fazla {max}",
    previewEmpty: "önizleme",
    timelineTitle: "Tespit edilen bölümler",
    statTotal: "Toplam", statKept: "Tutulan", statCut: "Kesilen",
    timelineEmpty: "Henüz analiz yok",
    legendKeep: "Konuşma / önemli an", legendCut: "Sessizlik / boş kısım",
    download: "İşlenmiş videoyu indir",
    settingsTitle: "Ayarlar",
    presetGame: "Oyun kaydı", presetInterview: "Röportaj", presetChat: "Sohbet",
    tabCut: "Kesim", tabAudio: "Ses", tabExport: "Dışa Aktar",
    thresholdLabel: "Sessizlik eşiği", thresholdHelp: "Bu seviyenin altındaki sesler boşluk sayılır",
    gapLabel: "Minimum boşluk süresi", gapHelp: "Bundan kısa boşluklar kesilmez",
    padLabel: "Pay bırak (kesimden önce/sonra)", padHelp: "Ani kesilmeleri önlemek için",
    fillerLabel: "Dolgu kelimeleri temizle", fillerDesc: "\u201Cıı\u201D, \u201Cşey\u201D gibi tekrarları tespit et",
    audioSource: "Ses kaynağı", audioSourceHelp: "Hangi ses izine göre kesileceğini seç (örn. mikrofon izi)",
    audioChannel: "Kanal", audioChannelHelp: "Stereo kayıtta mikrofon tek kanaldaysa onu seç",
    noAudioHelp: "Tek ses izi varsa varsayılan iz kullanılır, seçici gizlenir.",
    channelMix: "Karışık", channelLeft: "Sol", channelRight: "Sağ",
    audioTracks: "ses izi",
    auditionBtn: "Seçili izi dinle",
    auditionLoading: "Ses hazırlanıyor...",
    stageAnalyze: "analiz", stageRender: "kesiliyor",
    renderProgress: "{done}/{total} segment · {stage}",
    formatLabel: "Format",
    jsonBtn: "Kesim noktalarını JSON indir",
    analyzeBtn: "Analiz et", exportBtn: "Videoyu kes ve dışa aktar",
    secShort: "sn",
    fillerFound: "{n} dolgu kelime (%{p}) tespit edildi",
    fillerNone: "Dolgu kelime bulunamadı",
    fillerWorking: "Transkript analiz ediliyor...",
    summaryLine: "Yeni süre <b>{new}</b> · kazanılan <b>{saved} (%{pct})</b> · tahmini işlem <b>~{eta} sn</b> · tahmini bitiş <b>{finish}</b>",
    exportIdle: "Tahmini süre: analiz sonrası hesaplanır",
    exportReady: "Tahmini süre: ~{eta} · yerel işlem",
    renderWorking: (finish, left) => `İşleniyor... Tahmini bitiş: ${finish} (~${left} sn kaldı)`,
    renderFinishing: (finish) => `İşleniyor... bitmek üzere (${finish})`,
    uploadTooBig: "Dosya çok büyük. En fazla {max}.",
    errUpload: "Yükleme başarısız",
    analyzing: "Analiz ediliyor...",
    noFile: "Önce bir video yükleyin.",
  },
  en: {
    localBadge: "local analysis · no cloud",
    dropTitle: "Drop a video here or click to browse",
    dropHint: ".mp4 · .mkv · .mov · max {max}",
    previewEmpty: "preview",
    timelineTitle: "Detected sections",
    statTotal: "Total", statKept: "Kept", statCut: "Cut",
    timelineEmpty: "No analysis yet",
    legendKeep: "Speech / highlight", legendCut: "Silence / gap",
    download: "Download processed video",
    settingsTitle: "Settings",
    presetGame: "Gameplay", presetInterview: "Interview", presetChat: "Chat",
    tabCut: "Cut", tabAudio: "Audio", tabExport: "Export",
    thresholdLabel: "Silence threshold", thresholdHelp: "Audio below this level counts as gap",
    gapLabel: "Minimum gap length", gapHelp: "Shorter gaps are not cut",
    padLabel: "Padding (before/after each cut)", padHelp: "Prevents abrupt cuts",
    fillerLabel: "Remove filler words", fillerDesc: "Detect repetitions like \u201Cuh\u201D, \u201Clike\u201D",
    audioSource: "Audio source", audioSourceHelp: "Which audio track to cut by (e.g. the mic track)",
    audioChannel: "Channel", audioChannelHelp: "If the mic is on a single stereo channel, pick it",
    noAudioHelp: "With a single audio track the default is used and the picker stays hidden.",
    channelMix: "Mix", channelLeft: "Left", channelRight: "Right",
    audioTracks: "audio tracks",
    auditionBtn: "Listen to selected track",
    auditionLoading: "Preparing audio...",
    stageAnalyze: "analyzing", stageRender: "rendering",
    renderProgress: "{done}/{total} segments · {stage}",
    formatLabel: "Format",
    jsonBtn: "Download cut points as JSON",
    analyzeBtn: "Analyze", exportBtn: "Cut and export video",
    secShort: "s",
    fillerFound: "{n} filler words ({p}%) detected",
    fillerNone: "No filler words found",
    fillerWorking: "Analyzing transcript...",
    summaryLine: "New length <b>{new}</b> · saved <b>{saved} ({pct}%)</b> · est. render <b>~{eta}s</b> · est. finish <b>{finish}</b>",
    exportIdle: "Est. time: calculated after analysis",
    exportReady: "Est. time: ~{eta} · local processing",
    renderWorking: (finish, left) => `Rendering... Est. finish: ${finish} (~${left}s left)`,
    renderFinishing: (finish) => `Rendering... almost done (${finish})`,
    uploadTooBig: "File too large. Maximum is {max}.",
    errUpload: "Upload failed",
    analyzing: "Analyzing...",
    noFile: "Upload a video first.",
  },
};

const PRESETS = {
  game: { threshold: -42, minSilence: 1.2, padding: 0.18 },
  interview: { threshold: -35, minSilence: 0.6, padding: 0.15 },
  chat: { threshold: -40, minSilence: 0.8, padding: 0.2 },
};

let lang = localStorage.getItem("precutter-lang") || "tr";
let LIMITS = { max_upload_bytes: 4 * 1024 ** 3, max_video_duration: 4 * 3600, allowed_extensions: [".mp4", ".mkv", ".mov"] };

function t(key) { return (STR[lang] && STR[lang][key]) || STR.tr[key] || key; }

function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = t(el.dataset.i18n);
    if (typeof v === "string") el.textContent = v;
  });
  els.langTr.classList.toggle("active", lang === "tr");
  els.langEn.classList.toggle("active", lang === "en");
  localStorage.setItem("precutter-lang", lang);
  updateDropHint();
  syncSliders();
  refreshExportNote();
}

function setLang(next) { lang = next; applyLang(); }

/* ---------- helpers ---------- */
function fmtDur(seconds) {
  if (seconds == null || isNaN(seconds)) return "-";
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = (s % 60).toFixed(1).padStart(4, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}

function fmtRuler(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`
    : `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function fmtBytes(bytes) {
  if (bytes == null) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

function fmtClock(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = false;
}
function clearError() {
  els.error.hidden = true;
  els.error.textContent = "";
}

function setWorking(working) {
  els.renderBtn.disabled = working || !uploadedName;
  els.jsonBtn.disabled = working || !lastSummary;
}

function syncSliders() {
  els.thresholdValue.textContent = `${els.threshold.value} dB`;
  els.minSilenceValue.textContent = `${Number(els.minSilence.value).toFixed(1)} ${t("secShort")}`;
  els.paddingValue.textContent = `${Math.round(Number(els.padding.value) * 1000)} ms`;
}

function updateDropHint() {
  els.dropHint.textContent = t("dropHint").replace("{max}", fmtBytes(LIMITS.max_upload_bytes));
}

function params() {
  const ch = els.audioChannel ? els.audioChannel.value : "mix";
  return {
    filename: uploadedName,
    threshold_db: Number(els.threshold.value),
    min_silence: Number(els.minSilence.value),
    padding: Number(els.padding.value),
    audio_track: audioTrackIndex,
    audio_channel: ch === "mix" ? null : Number(ch),
  };
}

async function readError(response) {
  try {
    const data = await response.json();
    if (data && data.detail) return data.detail;
  } catch (e) { /* ignore */ }
  return `${t("errUpload")} (${response.status})`;
}

/* ---------- state ---------- */
let uploadedName = null;
let uploadedOriginal = null;
let uploadedDuration = null;
let lastEstimate = null;
let lastSummary = null;
let lastSegments = null;
let fillerOn = false;
let fillerFetchedFor = null;
let previewObjectUrl = null;
let audioTrackIndex = 0;
let audioStreams = [];
let activePreset = "game";

/* ---------- audio source ---------- */
function trackLabel(s) {
  const parts = [`Track ${s.track + 1}`, `${s.channels}ch`, s.codec];
  if (s.language && s.language !== "und") parts.push(s.language);
  if (s.title) parts.push(s.title);
  if (s.loudness_db != null) parts.push(`${s.loudness_db} dB`);
  return parts.join(" · ");
}

function setupAudioStreams(streams) {
  audioStreams = streams || [];
  audioTrackIndex = 0;
  if (els.audioChannel) els.audioChannel.value = "mix";
  const multi = audioStreams.length > 1;
  els.audioTrack.innerHTML = "";
  if (!multi) {
    els.noAudioHelp.hidden = false;
    els.channelField.hidden = true;
    return;
  }
  els.noAudioHelp.hidden = true;
  audioStreams.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = String(s.track);
    opt.textContent = trackLabel(s);
    els.audioTrack.appendChild(opt);
  });
  updateChannelField();
}

function updateChannelField() {
  const s = audioStreams[audioTrackIndex];
  const show = !!s && s.channels >= 2;
  els.channelField.hidden = !show;
  if (!show && els.audioChannel) els.audioChannel.value = "mix";
}

async function fetchAudioStreams() {
  // Upload yaniti hizli olmasi icin loudness icermez; arka planda zenginlestir.
  if (!uploadedName) return;
  try {
    const response = await fetch("/streams", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: uploadedName }),
    });
    if (!response.ok) return;
    const data = await response.json();
    if (data.audio_streams && data.audio_streams.length) {
      const keep = audioTrackIndex;
      setupAudioStreams(data.audio_streams);
      if (keep < audioStreams.length) {
        audioTrackIndex = keep;
        els.audioTrack.value = String(audioStreams[keep].track);
        updateChannelField();
      }
    }
  } catch (e) { /* secici sade kalir */ }
}

/* ---------- upload (XHR: progress bar) ---------- */
function uploadFile(file) {
  if (!file) return;
  if (file.size > LIMITS.max_upload_bytes) {
    showError(t("uploadTooBig").replace("{max}", fmtBytes(LIMITS.max_upload_bytes)));
    return;
  }
  clearError();
  resetResults();
  setWorking(true);
  els.uploadProgress.hidden = false;
  els.uploadFill.style.width = "0%";
  els.uploadPct.textContent = "0%";
  els.uploadSpeed.textContent = "";
  els.fileChip.hidden = true;

  const started = Date.now();
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload");
  xhr.upload.addEventListener("progress", (e) => {
    if (!e.lengthComputable) return;
    const pct = (e.loaded / e.total) * 100;
    els.uploadFill.style.width = `${pct.toFixed(1)}%`;
    els.uploadPct.textContent = `${pct.toFixed(0)}% · ${fmtBytes(e.loaded)} / ${fmtBytes(e.total)}`;
    const dt = (Date.now() - started) / 1000;
    if (dt > 0.5) els.uploadSpeed.textContent = `${fmtBytes(e.loaded / dt)}/s`;
  });
  xhr.addEventListener("load", () => {
    setWorking(false);
    if (xhr.status >= 200 && xhr.status < 300) {
      let data;
      try { data = JSON.parse(xhr.responseText); }
      catch (e) { showError(t("errUpload")); return; }
      uploadedName = data.filename;
      uploadedOriginal = data.original_name || file.name;
      uploadedDuration = data.duration_seconds;
      showFileChip(file, data);
      els.settingsSub.textContent = uploadedOriginal;
    } else {
      let msg = `${t("errUpload")} (${xhr.status})`;
      try {
        const data = JSON.parse(xhr.responseText);
        if (data && data.detail) msg = data.detail;
      } catch (e) { /* ignore */ }
      showError(msg);
      els.uploadProgress.hidden = true;
    }
    setWorking(false);
  });
  xhr.addEventListener("error", () => {
    setWorking(false);
    els.uploadProgress.hidden = true;
    showError(t("errUpload"));
  });
  const form = new FormData();
  form.append("file", file);
  xhr.send(form);

  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
  previewObjectUrl = URL.createObjectURL(file);
  els.previewVideo.src = previewObjectUrl;
  els.previewVideo.hidden = false;
  els.previewPlaceholder.hidden = true;
  els.previewTag.textContent = `${file.name}`;
  els.previewTag.hidden = false;
}

function showFileChip(file, data) {
  els.uploadProgress.hidden = true;
  els.fileChip.hidden = false;
  els.fileName.textContent = data.original_name || file.name;
  const dur = data.duration_seconds != null ? fmtDur(data.duration_seconds) : "?";
  const trackInfo = data.audio_streams && data.audio_streams.length > 1
    ? ` · ${data.audio_streams.length} ${t("audioTracks")}`
    : "";
  els.fileMeta.textContent = `${fmtBytes(file.size)} · ${dur}${trackInfo}`;
  if (data.audio_streams && data.audio_streams.length) {
    setupAudioStreams(data.audio_streams);
  }
  fetchAudioStreams();
  resetAudition();
  setWorking(false);
}

function removeFile() {
  uploadedName = null;
  uploadedOriginal = null;
  uploadedDuration = null;
  fillerFetchedFor = null;
  if (els.fillerSwitch.classList.contains("on")) toggleFiller(false);
  els.fileChip.hidden = true;
  els.uploadProgress.hidden = true;
  els.previewVideo.removeAttribute("src");
  els.previewVideo.hidden = true;
  els.previewPlaceholder.hidden = false;
  els.previewTag.hidden = true;
  els.fileInput.value = "";
  els.settingsSub.textContent = "-";
  resetAudition();
  resetResults();
  setWorking(false);
}

function resetResults() {
  els.timeline.querySelectorAll(".timeline-seg").forEach((el) => el.remove());
  els.timelineEmpty.hidden = false;
  els.ruler.hidden = true;
  els.ruler.innerHTML = "";
  els.statTotal.textContent = "-";
  els.statKept.textContent = "-";
  els.statCut.textContent = "-";
  els.summaryLine.hidden = true;
  els.downloadLink.hidden = true;
  els.fillerInfo.hidden = true;
  els.previewToggle.hidden = true;
  els.outputMeta.hidden = true;
  showingRendered = false;
  renderedUrl = null;
  lastEstimate = null;
  lastSummary = null;
  lastSegments = null;
  audioTrackIndex = 0;
  audioStreams = [];
  els.audioTrack.innerHTML = "";
  els.noAudioHelp.hidden = false;
  if (els.channelField) els.channelField.hidden = true;
  stopRenderCountdown();
  refreshExportNote();
  setWorking(false);
}

/* ---------- timeline ---------- */
function drawTimeline(segments, duration) {
  els.timeline.querySelectorAll(".timeline-seg").forEach((el) => el.remove());
  if (!duration || duration <= 0) return;
  els.timelineEmpty.hidden = true;

  const kept = segments.map(([s, e]) => ({
    start: Math.max(0, s),
    end: Math.min(duration, e),
  }));

  let cursor = 0;
  const pieces = [];
  for (const seg of kept) {
    if (seg.start > cursor) pieces.push({ cut: true, start: cursor, end: seg.start });
    if (seg.end > seg.start) pieces.push({ cut: false, start: seg.start, end: seg.end });
    cursor = Math.max(cursor, seg.end);
  }
  if (cursor < duration) pieces.push({ cut: true, start: cursor, end: duration });

  for (const piece of pieces) {
    const div = document.createElement("div");
    div.className = "timeline-seg" + (piece.cut ? " cut" : "");
    div.style.width = `${((piece.end - piece.start) / duration) * 100}%`;
    div.title = `${fmtRuler(piece.start)} → ${fmtRuler(piece.end)}`;
    els.timeline.appendChild(div);
  }

  els.ruler.innerHTML = "";
  for (let i = 0; i <= 5; i++) {
    const span = document.createElement("span");
    span.textContent = fmtRuler((duration * i) / 5);
    els.ruler.appendChild(span);
  }
  els.ruler.hidden = false;
}

function showSummary(summary) {
  lastSummary = summary;
  els.statTotal.textContent = fmtDur(summary.original_duration);
  els.statKept.textContent = fmtDur(summary.new_duration);
  els.statCut.textContent = fmtDur(summary.saved_seconds);
  const estimate = estimateSeconds(summary);
  lastEstimate = estimate;
  const finish = fmtClock(new Date(Date.now() + estimate * 1000));
  els.summaryLine.innerHTML = t("summaryLine")
    .replace("{new}", fmtDur(summary.new_duration))
    .replace("{saved}", summary.saved_seconds.toFixed(1) + "s")
    .replace("{pct}", summary.saved_percent)
    .replace("{eta}", estimate.toFixed(0))
    .replace("{finish}", finish);
  els.summaryLine.hidden = false;
  refreshExportNote();
  setWorking(false);
}

function refreshExportNote() {
  if (lastEstimate != null) {
    els.exportNote.textContent = t("exportReady").replace("{eta}", `~${lastEstimate.toFixed(0)}s`);
  } else {
    els.exportNote.textContent = t("exportIdle");
  }
}

function estimateSeconds(summary) {
  if (summary && summary.estimated_render_seconds != null) {
    return Number(summary.estimated_render_seconds);
  }
  const newDuration = summary ? Number(summary.new_duration || 0) : 0;
  const segCount = summary ? Number(summary.segment_count || 0) : 0;
  return 2.0 + newDuration * 0.4 + segCount * 0.15;
}

let renderTimer = null;
function startRenderCountdown(estimateSec) {
  stopRenderCountdown();
  const finish = Date.now() + estimateSec * 1000;
  const tick = () => {
    const left = Math.max(0, (finish - Date.now()) / 1000);
    els.renderStatus.hidden = false;
    els.renderStatus.textContent =
      left > 0
        ? t("renderWorking")(fmtClock(new Date(finish)), left.toFixed(0))
        : t("renderFinishing")(fmtClock(new Date(finish)));
  };
  tick();
  renderTimer = setInterval(tick, 500);
}
function stopRenderCountdown() {
  if (renderTimer) clearInterval(renderTimer);
  renderTimer = null;
  if (els.renderStatus) els.renderStatus.hidden = true;
}

/* ---------- analyze + render (tek tus) ---------- */
async function analyze() {
  if (!uploadedName) { showError(t("noFile")); return false; }
  clearError();
  setWorking(true);
  try {
    const response = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params()),
    });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    lastSegments = data.segments;
    drawTimeline(data.segments, data.duration);
    showSummary(data.summary);
    els.downloadLink.hidden = true;
    els.previewToggle.hidden = true;
    els.outputMeta.hidden = true;
    if (fillerOn) fetchFillers();
    return true;
  } catch (err) {
    showError(err.message);
    setWorking(false);
    return false;
  }
}

async function process() {
  // Tek tus: analiz et, zaman cizelgesini goster, hemen render isini baslat.
  if (!uploadedName) { showError(t("noFile")); return; }
  const ok = await analyze();
  if (ok) render();
}

async function render() {
  if (!uploadedName) { showError(t("noFile")); return; }
  clearError();
  setWorking(true);
  els.renderBtn.textContent = "...";
  els.renderProgress.hidden = false;
  els.renderFill.style.width = "0%";
  els.renderPct.textContent = "0%";
  try {
    const response = await fetch("/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params()),
    });
    if (!response.ok) throw new Error(await readError(response));
    const { job_id } = await response.json();
    await pollJob(job_id);
  } catch (err) {
    showError(err.message);
    els.renderProgress.hidden = true;
    els.renderBtn.textContent = t("exportBtn");
    setWorking(false);
  }
}

async function pollJob(jobId) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 1500));
    let job;
    try {
      const response = await fetch(`/jobs/${jobId}`);
      if (!response.ok) throw new Error(await readError(response));
      job = await response.json();
    } catch (err) {
      showError(err.message);
      break;
    }
    if (job.total) {
      const pct = (job.done / job.total) * 100;
      els.renderFill.style.width = `${pct.toFixed(1)}%`;
      els.renderPct.textContent = `${pct.toFixed(0)}%`;
      els.renderStage.textContent = t(job.stage === "render" ? "stageRender" : "stageAnalyze");
    }
    if (job.status === "done") {
      els.renderFill.style.width = "100%";
      els.renderPct.textContent = "100%";
      lastEstimate = estimateSeconds(job.summary);
      lastSegments = null;
      showSummary(job.summary);
      els.downloadLink.href = job.download_url;
      els.downloadLink.hidden = false;
      showRenderedPreview(job);
      setTimeout(() => { els.renderProgress.hidden = true; }, 4000);
      break;
    }
    if (job.status === "error") {
      showError(job.error || t("errUpload"));
      els.renderProgress.hidden = true;
      break;
    }
  }
  els.renderBtn.textContent = t("exportBtn");
  setWorking(false);
}

/* ---------- rendered preview toggle ---------- */
let showingRendered = false;
let renderedUrl = null;

function showRenderedPreview(job) {
  renderedUrl = job.download_url;
  showingRendered = true;
  els.previewVideo.src = renderedUrl;
  els.previewVideo.hidden = false;
  els.previewPlaceholder.hidden = true;
  els.previewTag.textContent = t("previewResult");
  els.previewTag.hidden = false;
  els.previewToggle.hidden = false;
  els.previewToggle.textContent = t("showOriginal");
  if (job.output_audio_tracks != null) {
    els.outputMeta.textContent = t("outputTracks").replace("{n}", job.output_audio_tracks);
    els.outputMeta.hidden = false;
  }
}

function togglePreview() {
  if (!renderedUrl) return;
  showingRendered = !showingRendered;
  if (showingRendered) {
    els.previewVideo.src = renderedUrl;
    els.previewTag.textContent = t("previewResult");
    els.previewToggle.textContent = t("showOriginal");
  } else if (previewObjectUrl) {
    els.previewVideo.src = previewObjectUrl;
    els.previewTag.textContent = uploadedOriginal || "";
    els.previewToggle.textContent = t("showResult");
  } else if (uploadedName) {
    els.previewVideo.src = `/media/${encodeURIComponent(uploadedName)}`;
    els.previewTag.textContent = uploadedOriginal || "";
    els.previewToggle.textContent = t("showResult");
  }
}

async function fetchFillers() {
  if (!uploadedName || fillerFetchedFor === uploadedName) return;
  els.fillerInfo.hidden = false;
  els.fillerInfo.textContent = t("fillerWorking");
  try {
    const response = await fetch("/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: uploadedName, remove_fillers: true, audio_track: audioTrackIndex }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    fillerFetchedFor = uploadedName;
    const n = (data.fillers || []).length;
    els.fillerInfo.textContent =
      n > 0
        ? t("fillerFound").replace("{n}", n).replace("{p}", (data.filler_ratio * 100).toFixed(1))
        : t("fillerNone");
  } catch (err) {
    els.fillerInfo.textContent = err.message;
  }
}

function toggleFiller(force) {
  fillerOn = force !== undefined ? force : !els.fillerSwitch.classList.contains("on");
  els.fillerSwitch.classList.toggle("on", fillerOn);
  els.fillerSwitch.setAttribute("aria-checked", String(fillerOn));
  if (!fillerOn) {
    els.fillerInfo.hidden = true;
  } else if (uploadedName) {
    fetchFillers();
  }
}

function downloadJson() {
  if (!lastSummary || !lastSegments) return;
  const payload = {
    source: uploadedOriginal || uploadedName,
    params: params(),
    segments: lastSegments,
    summary: lastSummary,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "precutter-cuts.json";
  a.click();
  URL.revokeObjectURL(url);
}

/* ---------- presets & tabs ---------- */
function applyPreset(name) {
  const p = PRESETS[name];
  if (!p) return;
  activePreset = name;
  els.threshold.value = p.threshold;
  els.minSilence.value = p.minSilence;
  els.padding.value = p.padding;
  document.querySelectorAll(".preset-chip").forEach((c) =>
    c.classList.toggle("active", c.dataset.preset === name)
  );
  syncSliders();
}

/* ---------- track audition ---------- */
function resetAudition() {
  els.auditionAudio.removeAttribute("src");
  els.auditionAudio.hidden = true;
  els.auditionStatus.hidden = true;
  els.auditionBtn.disabled = !uploadedName;
}

async function audition() {
  if (!uploadedName) { showError(t("noFile")); return; }
  clearError();
  els.auditionStatus.hidden = false;
  els.auditionStatus.textContent = t("auditionLoading");
  els.auditionBtn.disabled = true;
  try {
    // Onizleme dosyasi sunucuda hazirlanir (ilk seferde biraz surer), sonra oynatilir.
    const url = `/preview-audio/${encodeURIComponent(uploadedName)}?track=${audioTrackIndex}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(await readError(response));
    const blob = await response.blob();
    els.auditionAudio.src = URL.createObjectURL(blob);
    els.auditionAudio.hidden = false;
    els.auditionStatus.hidden = true;
    els.auditionAudio.play().catch(() => {});
  } catch (err) {
    els.auditionStatus.textContent = err.message;
  } finally {
    els.auditionBtn.disabled = !uploadedName;
  }
}

/* ---------- events ---------- */
els.fileInput.addEventListener("change", (e) => uploadFile(e.target.files[0]));
els.fileRemove.addEventListener("click", removeFile);

["dragenter", "dragover"].forEach((evt) =>
  els.drop.addEventListener(evt, (e) => {
    e.preventDefault();
    els.drop.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  els.drop.addEventListener(evt, (e) => {
    e.preventDefault();
    els.drop.classList.remove("dragover");
  })
);
els.drop.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});

[els.threshold, els.minSilence, els.padding].forEach((slider) =>
  slider.addEventListener("input", () => {
    syncSliders();
    document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
  })
);
document.querySelectorAll(".preset-chip").forEach((chip) =>
  chip.addEventListener("click", () => applyPreset(chip.dataset.preset))
);

document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((x) => x.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`.tab-panel[data-panel="${tab.dataset.tab}"]`).classList.add("active");
  })
);

els.fillerSwitch.addEventListener("click", () => toggleFiller());
els.fillerSwitch.addEventListener("keydown", (e) => {
  if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggleFiller(); }
});

els.audioTrack.addEventListener("change", () => {
  audioTrackIndex = Number(els.audioTrack.value) || 0;
  fillerFetchedFor = null;
  updateChannelField();
  resetAudition();
  if (lastSummary) resetResults();
});
els.audioChannel.addEventListener("change", () => {
  if (lastSummary) resetResults();
});
els.auditionBtn.addEventListener("click", audition);

els.renderBtn.addEventListener("click", process);
els.previewToggle.addEventListener("click", togglePreview);
els.jsonBtn.addEventListener("click", downloadJson);
els.langTr.addEventListener("click", () => setLang("tr"));
els.langEn.addEventListener("click", () => setLang("en"));

/* ---------- init ---------- */
async function init() {
  try {
    const response = await fetch("/health");
    if (response.ok) {
      const data = await response.json();
      if (data.limits) LIMITS = data.limits;
    }
  } catch (e) { /* varsayılan limitlerle devam */ }
  applyPreset("game");
  applyLang();
  resetAudition();
  setWorking(false);
}

init();
