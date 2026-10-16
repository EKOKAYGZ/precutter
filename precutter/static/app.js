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
  uploadCard: document.getElementById("uploadCard"),
  fileTopbar: document.getElementById("fileTopbar"),
  topFileName: document.getElementById("topFileName"),
  topFileMeta: document.getElementById("topFileMeta"),
  changeFileBtn: document.getElementById("changeFileBtn"),
  importToggle: document.getElementById("importToggle"),
  importForm: document.getElementById("importForm"),
  importPath: document.getElementById("importPath"),
  importBtn: document.getElementById("importBtn"),
  browseBtn: document.getElementById("browseBtn"),
  browseModal: document.getElementById("browseModal"),
  browseClose: document.getElementById("browseClose"),
  browsePath: document.getElementById("browsePath"),
  browseList: document.getElementById("browseList"),
  browseNote: document.getElementById("browseNote"),
  previewVideo: document.getElementById("previewVideo"),
  previewPlaceholder: document.getElementById("previewPlaceholder"),
  previewTag: document.getElementById("previewTag"),
  threshold: document.getElementById("threshold"),
  thresholdValue: document.getElementById("thresholdValue"),
  minSilence: document.getElementById("minSilence"),
  minSilenceValue: document.getElementById("minSilenceValue"),
  paddingPre: document.getElementById("paddingPre"),
  paddingPreValue: document.getElementById("paddingPreValue"),
  paddingPost: document.getElementById("paddingPost"),
  paddingPostValue: document.getElementById("paddingPostValue"),
  settingsSub: document.getElementById("settingsSub"),
  presetRow: document.getElementById("presetRow"),
  fillerSwitch: document.getElementById("fillerSwitch"),
  fillerInfo: document.getElementById("fillerInfo"),
  subtitleSwitch: document.getElementById("subtitleSwitch"),
  aiCutSwitch: document.getElementById("aiCutSwitch"),
  aiThreshold: document.getElementById("aiThreshold"),
  aiThresholdValue: document.getElementById("aiThresholdValue"),
  aiInfo: document.getElementById("aiInfo"),
  aiContent: document.getElementById("aiContent"),
  chatLog: document.getElementById("chatLog"),
  chatInput: document.getElementById("chatInput"),
  chatSend: document.getElementById("chatSend"),
  audioTrack: document.getElementById("audioTrack"),
  channelField: document.getElementById("channelField"),
  audioChannel: document.getElementById("audioChannel"),
  noAudioHelp: document.getElementById("noAudioHelp"),
  auditionBtn: document.getElementById("auditionBtn"),
  auditionStatus: document.getElementById("auditionStatus"),
  auditionAudio: document.getElementById("auditionAudio"),
  jsonBtn: document.getElementById("jsonBtn"),
  srtBtn: document.getElementById("srtBtn"),
  analyzeBtn: document.getElementById("analyzeBtn"),
  renderBtn: document.getElementById("renderBtn"),
  exportNote: document.getElementById("exportNote"),
  playerBar: document.getElementById("playerBar"),
  proxyNote: document.getElementById("proxyNote"),
  outputMeta: document.getElementById("outputMeta"),
  analysisStatus: document.getElementById("analysisStatus"),
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
  navSettings: document.getElementById("navSettings"),
  settingsModal: document.getElementById("settingsModal"),
  settingsClose: document.getElementById("settingsClose"),
  settingsCancel: document.getElementById("settingsCancel"),
  settingsSave: document.getElementById("settingsSave"),
  settingsNote: document.getElementById("settingsNote"),
  setThreshold: document.getElementById("setThreshold"),
  setThresholdVal: document.getElementById("setThresholdVal"),
  setMinSilence: document.getElementById("setMinSilence"),
  setMinSilenceVal: document.getElementById("setMinSilenceVal"),
  setPaddingPre: document.getElementById("setPaddingPre"),
  setPaddingPreVal: document.getElementById("setPaddingPreVal"),
  setPaddingPost: document.getElementById("setPaddingPost"),
  setPaddingPostVal: document.getElementById("setPaddingPostVal"),
  setQuality: document.getElementById("setQuality"),
  setOutputAudio: document.getElementById("setOutputAudio"),
  doctorBox: document.getElementById("doctorBox"),
  setWhisper: document.getElementById("setWhisper"),
  setEncoder: document.getElementById("setEncoder"),
  setMaxUpload: document.getElementById("setMaxUpload"),
  setMaxUploadVal: document.getElementById("setMaxUploadVal"),
  setOllama: document.getElementById("setOllama"),
  setAiModel: document.getElementById("setAiModel"),
  setAiThreshold: document.getElementById("setAiThreshold"),
  setAiThresholdVal: document.getElementById("setAiThresholdVal"),
  setPreviewVideo: document.getElementById("setPreviewVideo"),
  storageList: document.getElementById("storageList"),
  storageTotal: document.getElementById("storageTotal"),
  clearCacheBtn: document.getElementById("clearCacheBtn"),
  clearAllBtn: document.getElementById("clearAllBtn"),
};

// Eski önbellekli HTML + yeni JS karışırsa tek bir eksik eleman tüm
// uygulamayı öldürmesin: eksikleri zararsız kuklayla değiştir, konsola
// error yaz ve sayfada görünür uyarı göster (sessiz kalma).
(function guardEls() {
  const dummy = {
    addEventListener() {},
    removeAttribute() {},
    setAttribute() {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  };
  const missing = [];
  for (const k of Object.keys(els)) {
    if (!els[k]) {
      missing.push(k);
      els[k] = dummy;
    }
  }
  if (missing.length) {
    console.error("PreCutter: missing elements (stale page cache?): " + missing.join(", "));
    try {
      const banner = document.createElement("div");
      banner.className = "stale-warning";
      banner.textContent = "PreCutter: page/JS mismatch (" + missing.join(", ") +
        ") — hard-refresh the page (Ctrl+F5).";
      document.body.prepend(banner);
    } catch (e) { /* DOM yoksa sessiz */ }
  }
})();

/* ---------- i18n ---------- */
const STR = {
  tr: {
    localBadge: "yerel analiz · bulut yok",
    dropTitle: "Videoyu buraya bırak veya gözatmak için tıkla",
    dropHint: ".mp4 · .mkv · .mov · en fazla {max}",
    previewEmpty: "önizleme",
    timelineTitle: "Tespit edilen bölümler",
    statusIdle: "Analiz bekleniyor",
    statusWorking: "Analiz ediliyor…",
    statusDone: "Analiz edildi",
    statusStale: "Ayarlar değişti — tekrar analiz et",
    statTotal: "Toplam", statKept: "Tutulan", statCut: "Kesilen",
    timelineEmpty: "Henüz analiz yok",
    legendKeep: "Konuşma / önemli an", legendCut: "Sessizlik / boş kısım",
    download: "İşlenmiş videoyu indir",
    settingsTitle: "Ayarlar",
    presetGame: "Oyun kaydı", presetInterview: "Röportaj", presetChat: "Sohbet",
    tabCut: "Kesim", tabAudio: "Ses", tabExport: "Dışa Aktar",
    thresholdLabel: "Sessizlik eşiği", thresholdHelp: "Bu seviyenin altındaki sesler boşluk sayılır",
    gapLabel: "Minimum boşluk süresi", gapHelp: "Bundan kısa boşluklar kesilmez",
    padPreLabel: "Pay bırak (kesimden önce)", padPreHelp: "Konuşma başlangıcı kırpılmasın diye",
    padPostLabel: "Pay bırak (kesimden sonra)", padPostHelp: "Ani kesilmeleri önlemek için",
    legendFiller: "Dolgu kelime kesimi", legendMusic: "Müzik", legendHighlight: "Öne çıkan an",
    modeOriginal: "Orijinal", modeCut: "Kesim önizleme", modeRendered: "İşlenmiş",
    zoomLabel: "Yakınlaştırma",
    srtBtn: "Altyazıyı SRT indir",
    qualityLabel: "Kalite",
    qualityMatch: "Kaynakla eşleş (öneri)", qualityHigh: "Yüksek", qualitySmall: "Küçük dosya",
    outputAudioLabel: "Çıktı sesi",
    outputAudioMix: "Karışık: mikrofon + oyun (varsayılan)",
    outputAudioSeparate: "Ayrı izler, mikrofon varsayılan",
    outputAudioMicOnly: "Sadece mikrofon",
    doctorTitle: "Sistem durumu", doctorLoading: "Yükleniyor…", freeDisk: "Boş disk",
    padLabel: "Pay bırak (kesimden önce/sonra)", padHelp: "Ani kesilmeleri önlemek için",
    fillerLabel: "Dolgu kelimeleri temizle", fillerDesc: "\u201Cıı\u201D, \u201Cşey\u201D gibi tekrarları tespit et",
    subtitleLabel: "Altyazı oluştur (SRT)", subtitleDesc: "Konuşma metnini kesim planına işle",
    stageSilence: "sessizlik taranıyor", stageTranscribe: "transkript yazılıyor",
    stageEvents: "ses olayları taranıyor", stageProxy: "önizleme",
    subtitleReady: "Altyazı hazır ({n} kelime)",
    srtNoTranscript: "Altyazı yok — önce Altyazı seçeneğini açıp Analiz Et.",
    importToggle: "Dosya yolundan ekle (kopyalamadan)",
    importBtn: "Ekle",
    importHelp: "Aynı bilgisayardaki dosyayı karşıya yüklemeden bağlar — büyük dosyalarda anında açılır.",
    importPH: "Örn. C:\\Videolar\\kayit.mp4",
    tabAI: "AI",
    aiLabel: "AI ile önemsiz yerleri kes",
    aiDesc: "Transkripti puanlar, düşük skorluları atar (Ollama)",
    aiThresholdLabel: "AI kesim eşiği",
    aiThresholdHelp: "Bu puanın altındaki bölümler kesilir",
    legendAI: "AI kesimi",
    stageAI: "AI puanlıyor",
    aiCutFound: "{n} önemsiz bölüm kesildi (AI: {src})",
    aiContentLabel: "Tespit edilen içerik",
    aiContentNone: "Analiz sonrası belli olur",
    chatSend: "Sor",
    chatPH: "Video hakkında sor…",
    chatHelp: "Video hakkında sor (transkript + puanlar kullanılır). Ollama gerekli.",
    chatTyping: "AI yazıyor…",
    chatNeedFile: "Önce bir video yükleyin.",
    chatYou: "Sen",
    preaiSub: "Video asistanı — transkript ve puanlarla cevaplar",
    proxyPreparing: "Önizleme hazırlanıyor %{p}…",
    proxyReady: "Önizleme hazır",
    changeFile: "Dosya değiştir",
    ollamaHost: "Ollama adresi",
    aiModel: "AI modeli",
    aiThreshold: "AI kesim eşiği",
    previewVideo: "Önizleme videosu (720p proxy)",
    previewVideoHelp: "Kapalıyken önizleme doğrudan kaynaktan oynar — hızlı. Büyük dosyalarda açmak oynatmayı hafifletir ama videonu yeniden kodlar.",
    browseTitle: "Dosya seç",
    browseBtn: "Gözat",
    browseEmpty: "Burada video yok.",
    browseUp: "↑ Üst klasör",
    browseRoots: "Sürücüler",
    audioSource: "Ses kaynağı", audioSourceHelp: "Hangi ses izine göre kesileceğini seç (örn. mikrofon izi)",
    micHint: "(mikrofon?)",
    audioChannel: "Kanal", audioChannelHelp: "Stereo kayıtta mikrofon tek kanaldaysa onu seç",
    noAudioHelp: "Tek ses izi varsa varsayılan iz kullanılır, seçici gizlenir.",
    channelMix: "Karışık", channelLeft: "Sol", channelRight: "Sağ",
    audioTracks: "ses izi",
    auditionBtn: "Seçili izi dinle",
    auditionLoading: "Ses hazırlanıyor...",
    stageAnalyze: "analiz", stageRender: "kesiliyor",
    stageQueued: "sırada",
    renderProgress: "{done}/{total} segment · {stage}",
    formatLabel: "Format",
    jsonBtn: "Kesim noktalarını JSON indir",
    analyzeBtn: "Analiz Et",
    exportBtn: "Videoyu kes ve dışa aktar",
    secShort: "sn",
    fillerFound: "{n} dolgu kelime (%{p}) tespit edildi",
    fillerNone: "Dolgu kelime bulunamadı",
    fillerWorking: "Transkript analiz ediliyor...",
    transcriptProgress: "Transkript %{p}…",
    summaryLine: "Yeni süre <b>{new}</b> · kazanılan <b>{saved} (%{pct})</b> · tahmini işlem <b>~{eta} sn</b> · tahmini bitiş <b>{finish}</b>",
    exportIdle: "Tahmini süre: analiz sonrası hesaplanır",
    exportReady: "Tahmini süre: ~{eta} · yerel işlem",
    renderWorking: (finish, left) => `İşleniyor... Tahmini bitiş: ${finish} (~${left} sn kaldı)`,
    renderFinishing: (finish) => `İşleniyor... bitmek üzere (${finish})`,
    uploadTooBig: "Dosya çok büyük. En fazla {max}.",
    errUpload: "Yükleme başarısız",
    noFile: "Önce bir video yükleyin.",
    previewResult: "kesilmiş önizleme",
    showOriginal: "Orijinali göster",
    showResult: "Kesilmişi göster",
    outputTracks: "Çıktıda {n} ses izi",
    settingsModalTitle: "Uygulama ayarları",
    settingsDefaults: "Varsayılan kesim değerleri",
    settingsEngine: "Motor",
    padLabelShort: "Pay bırak",
    padPostShort: "Pay bırak (sonra)",
    whisperModel: "Whisper modeli",
    encoderPref: "Video kodlayıcı",
    encoderAuto: "Otomatik (NVENC varsa)",
    maxUpload: "En fazla yükleme (GB)",
    storageTitle: "Depolama",
    storageEmpty: "Yüklenmiş dosya yok.",
    clearCache: "Önbelleği temizle",
    clearAll: "Tümünü sil",
    cancelBtn: "Vazgeç",
    saveBtn: "Kaydet",
    settingsSaved: "Ayarlar kaydedildi.",
    confirmClearAll: "Tüm yüklemeler, çıktılar ve önbellek silinsin mi?",
    freedBytes: "{x} temizlendi",
  },
  en: {
    localBadge: "local analysis · no cloud",
    dropTitle: "Drop a video here or click to browse",
    dropHint: ".mp4 · .mkv · .mov · max {max}",
    previewEmpty: "preview",
    timelineTitle: "Detected sections",
    statusIdle: "Waiting for analysis",
    statusWorking: "Analyzing…",
    statusDone: "Analyzed",
    statusStale: "Settings changed — analyze again",
    statTotal: "Total", statKept: "Kept", statCut: "Cut",
    timelineEmpty: "No analysis yet",
    legendKeep: "Speech / highlight", legendCut: "Silence / gap",
    download: "Download processed video",
    settingsTitle: "Settings",
    presetGame: "Gameplay", presetInterview: "Interview", presetChat: "Chat",
    tabCut: "Cut", tabAudio: "Audio", tabExport: "Export",
    thresholdLabel: "Silence threshold", thresholdHelp: "Audio below this level counts as gap",
    gapLabel: "Minimum gap length", gapHelp: "Shorter gaps are not cut",
    padPreLabel: "Padding (before cut)", padPreHelp: "Keeps speech starts intact",
    padPostLabel: "Padding (after cut)", padPostHelp: "Prevents abrupt cuts",
    legendFiller: "Filler-word cut", legendMusic: "Music", legendHighlight: "Highlight",
    modeOriginal: "Original", modeCut: "Cut preview", modeRendered: "Rendered",
    zoomLabel: "Zoom",
    srtBtn: "Download subtitles as SRT",
    qualityLabel: "Quality",
    qualityMatch: "Match source (recommended)", qualityHigh: "High", qualitySmall: "Small file",
    outputAudioLabel: "Output audio",
    outputAudioMix: "Mix: mic + game (default)",
    outputAudioSeparate: "Separate tracks, mic default",
    outputAudioMicOnly: "Mic only",
    doctorTitle: "System status", doctorLoading: "Loading…", freeDisk: "Free disk",
    padLabel: "Padding (before/after each cut)", padHelp: "Prevents abrupt cuts",
    fillerLabel: "Remove filler words", fillerDesc: "Detect repetitions like \u201Cuh\u201D, \u201Clike\u201D",
    subtitleLabel: "Generate subtitles (SRT)", subtitleDesc: "Transcribe speech for the cut timeline",
    stageSilence: "scanning silence", stageTranscribe: "transcribing",
    stageEvents: "spotting sound events", stageProxy: "preview",
    subtitleReady: "Subtitles ready ({n} words)",
    srtNoTranscript: "No transcript — enable Subtitles and Analyze first.",
    importToggle: "Add by file path (no copy)",
    importBtn: "Add",
    importHelp: "Links a file on this machine without uploading — instant for big files.",
    importPH: "E.g. C:\\Videos\\recording.mp4",
    tabAI: "AI",
    aiLabel: "Cut boring parts with AI",
    aiDesc: "Scores the transcript, drops low scores (Ollama)",
    aiThresholdLabel: "AI cut threshold",
    aiThresholdHelp: "Parts below this score are cut",
    legendAI: "AI cut",
    stageAI: "AI scoring",
    aiCutFound: "{n} boring parts cut (AI: {src})",
    aiContentLabel: "Detected content",
    aiContentNone: "Shown after analysis",
    chatSend: "Ask",
    chatPH: "Ask about the video…",
    chatHelp: "Ask about the video (uses transcript + scores). Needs Ollama.",
    chatTyping: "AI is typing…",
    chatNeedFile: "Upload a video first.",
    chatYou: "You",
    preaiSub: "Video assistant — answers from transcript and scores",
    proxyPreparing: "Preparing preview %{p}…",
    proxyReady: "Preview ready",
    changeFile: "Change file",
    ollamaHost: "Ollama address",
    aiModel: "AI model",
    aiThreshold: "AI cut threshold",
    previewVideo: "Preview video (720p proxy)",
    previewVideoHelp: "Off = play straight from the source (fast). Enabling on large files lightens playback but re-encodes your video.",
    browseTitle: "Pick a file",
    browseBtn: "Browse",
    browseEmpty: "No videos here.",
    browseUp: "↑ Up",
    browseRoots: "Drives",
    audioSource: "Audio source", audioSourceHelp: "Which audio track to cut by (e.g. the mic track)",
    micHint: "(mic?)",
    audioChannel: "Channel", audioChannelHelp: "If the mic is on a single stereo channel, pick it",
    noAudioHelp: "With a single audio track the default is used and the picker stays hidden.",
    channelMix: "Mix", channelLeft: "Left", channelRight: "Right",
    audioTracks: "audio tracks",
    auditionBtn: "Listen to selected track",
    auditionLoading: "Preparing audio...",
    stageAnalyze: "analyzing", stageRender: "rendering",
    stageQueued: "queued",
    renderProgress: "{done}/{total} segments · {stage}",
    formatLabel: "Format",
    jsonBtn: "Download cut points as JSON",
    analyzeBtn: "Analyze",
    exportBtn: "Cut and export video",
    secShort: "s",
    fillerFound: "{n} filler words ({p}%) detected",
    fillerNone: "No filler words found",
    fillerWorking: "Analyzing transcript...",
    transcriptProgress: "Transcript %{p}…",
    summaryLine: "New length <b>{new}</b> · saved <b>{saved} ({pct}%)</b> · est. render <b>~{eta}s</b> · est. finish <b>{finish}</b>",
    exportIdle: "Est. time: calculated after analysis",
    exportReady: "Est. time: ~{eta} · local processing",
    renderWorking: (finish, left) => `Rendering... Est. finish: ${finish} (~${left}s left)`,
    renderFinishing: (finish) => `Rendering... almost done (${finish})`,
    uploadTooBig: "File too large. Maximum is {max}.",
    errUpload: "Upload failed",
    noFile: "Upload a video first.",
    previewResult: "cut preview",
    showOriginal: "Show original",
    showResult: "Show result",
    outputTracks: "{n} audio tracks in output",
    settingsModalTitle: "App settings",
    settingsDefaults: "Default cut values",
    settingsEngine: "Engine",
    padLabelShort: "Padding",
    padPostShort: "Padding (after)",
    whisperModel: "Whisper model",
    encoderPref: "Video encoder",
    encoderAuto: "Auto (NVENC if available)",
    maxUpload: "Max upload (GB)",
    storageTitle: "Storage",
    storageEmpty: "No uploaded files.",
    clearCache: "Clear cache",
    clearAll: "Delete all",
    cancelBtn: "Cancel",
    saveBtn: "Save",
    settingsSaved: "Settings saved.",
    confirmClearAll: "Delete all uploads, outputs and cache?",
    freedBytes: "{x} freed",
  },
};

const PRESETS = {
  game: { threshold: -40, minSilence: 0.8, paddingPre: 0.2, paddingPost: 0.25 },
  interview: { threshold: -35, minSilence: 0.6, paddingPre: 0.15, paddingPost: 0.2 },
  chat: { threshold: -38, minSilence: 0.7, paddingPre: 0.2, paddingPost: 0.25 },
};

let lang = localStorage.getItem("precutter-lang") || "en";
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
  if (els.importPath) els.importPath.placeholder = t("importPH");
  if (els.chatInput) els.chatInput.placeholder = t("chatPH");
  localStorage.setItem("precutter-lang", lang);
  updateDropHint();
  syncSliders();
  refreshExportNote();
  setAnalysisState(analysisState, analysisDetail);
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
  isWorking = working;
  els.analyzeBtn.disabled = working || !uploadedName;
  els.renderBtn.disabled = working || !uploadedName || !lastSummary;
  els.jsonBtn.disabled = working || !lastSummary;
  els.srtBtn.disabled = working || !hasTranscript;
  els.chatSend.disabled = working || !uploadedName;
}

function setAnalysisState(state, detail) {
  analysisState = state;
  if (detail !== undefined) analysisDetail = detail;
  els.analysisStatus.className = "analysis-status " + state;
  const label = t("status" + state[0].toUpperCase() + state.slice(1));
  els.analysisStatus.textContent = analysisDetail ? `${label} · ${analysisDetail}` : label;
}

function markStale() {
  if (lastSummary && !isWorking) setAnalysisState("stale");
}

function syncSliders() {
  els.thresholdValue.textContent = `${els.threshold.value} dB`;
  els.minSilenceValue.textContent = `${Number(els.minSilence.value).toFixed(1)} ${t("secShort")}`;
  els.paddingPreValue.textContent = `${Math.round(Number(els.paddingPre.value) * 1000)} ms`;
  els.paddingPostValue.textContent = `${Math.round(Number(els.paddingPost.value) * 1000)} ms`;
}

function updateDropHint() {
  els.dropHint.textContent = t("dropHint").replace("{max}", fmtBytes(LIMITS.max_upload_bytes));
}

function params(forRender = false) {
  const ch = els.audioChannel ? els.audioChannel.value : "mix";
  const body = {
    filename: uploadedName,
    threshold_db: Number(els.threshold.value),
    min_silence: Number(els.minSilence.value),
    padding_pre: Number(els.paddingPre.value),
    padding_post: Number(els.paddingPost.value),
    audio_track: audioTrackIndex,
    audio_channel: ch === "mix" ? null : Number(ch),
    remove_fillers: fillerOn,
    make_subtitles: subtitleOn,
    ai_cut: aiCutOn,
    ai_threshold: Number(els.aiThreshold ? els.aiThreshold.value : 30),
  };
  if (forRender && lastSegments && lastSegments.length) {
    // View-only: render her zaman son analiz zaman çizelgesini gönderir,
    // analiz tekrar koşmaz.
    body.manual_segments = lastSegments;
  }
  return body;
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
let uploadedSize = null;
let lastEstimate = null;
let lastSummary = null;
let lastSegments = null;
let lastAnalysis = null;
let lastCuts = [];
let lastMusic = [];
let lastFps = 30;
let fillerOn = false;
let fillerFetchedFor = null;
let fillerJobRunning = false;
let subtitleOn = false;
let aiCutOn = false;
let chatHistory = [];
let hasTranscript = false;
let transcriptWords = 0;
let previewObjectUrl = null;
let audioTrackIndex = 0;
let audioStreams = [];
let userPickedTrack = false;
let activePreset = "game";
let isWorking = false;
let analysisState = "idle";
let analysisDetail = "";

/* ---------- audio source ---------- */
function trackLabel(s, isSuggested) {
  const parts = [`Track ${s.track + 1}`, `${s.channels}ch`, s.codec];
  if (s.language && s.language !== "und") parts.push(s.language);
  if (s.title) parts.push(s.title);
  if (s.loudness_db != null) parts.push(`${s.loudness_db} dB`);
  if (isSuggested) parts.push(t("micHint"));
  return parts.join(" · ");
}

function setupAudioStreams(streams, suggested) {
  audioStreams = streams || [];
  if (!userPickedTrack && suggested != null && suggested < audioStreams.length) {
    audioTrackIndex = suggested;
  } else if (audioTrackIndex >= audioStreams.length) {
    audioTrackIndex = 0;
  }
  // Kullanıcının kanal seçimini koru: yeni izde de geçerliyse aynen bırak.
  const prevChannel = els.audioChannel ? els.audioChannel.value : "mix";
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
    opt.textContent = trackLabel(s, s.track === suggested);
    els.audioTrack.appendChild(opt);
  });
  els.audioTrack.value = String(audioStreams[audioTrackIndex].track);
  updateChannelField();
  // Kanal seçici açıksa ve önceki seçim hâlâ geçerliyse geri yükle.
  if (!els.channelField.hidden && els.audioChannel) {
    if (prevChannel === "0" || prevChannel === "1" || prevChannel === "mix") {
      els.audioChannel.value = prevChannel;
    }
  }
}

function updateChannelField() {
  const s = audioStreams[audioTrackIndex];
  const show = !!s && s.channels >= 2;
  els.channelField.hidden = !show;
  if (!show && els.audioChannel) els.audioChannel.value = "mix";
}

async function fetchAudioStreams() {
  // Upload yanıtı hızlı olması için loudness içermez; arka planda zenginleştir.
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
      setupAudioStreams(data.audio_streams, data.suggested_mic);
      updateChannelField();
      if (window.PrecutterPlayer) {
        window.PrecutterPlayer.setAudioTracks(data.audio_streams, audioTrackIndex, uploadedName);
      }
    }
  } catch (e) { /* seçici sade kalır */ }
}

/* ---------- dosya hazır: upload ve yoldan ekleme burada birleşir ---------- */
function afterFileReady(data, name, size, previewSrc) {
  uploadedName = data.filename;
  uploadedOriginal = data.original_name || name;
  uploadedDuration = data.duration_seconds;
  uploadedSize = data.size_bytes != null ? data.size_bytes : (size || null);
  showFileChip({ name: uploadedOriginal, size: uploadedSize || 0 }, data);
  els.settingsSub.textContent = uploadedOriginal;
  if (previewSrc) {
    if (previewObjectUrl) { URL.revokeObjectURL(previewObjectUrl); previewObjectUrl = null; }
    els.previewVideo.src = previewSrc;
    els.previewVideo.hidden = false;
    els.previewPlaceholder.hidden = true;
    els.previewTag.textContent = uploadedOriginal;
    els.previewTag.hidden = false;
  }
  chatHistory = [];
  if (els.chatLog) els.chatLog.innerHTML = "";
  els.playerBar.hidden = false;
  els.uploadCard.hidden = true;
  els.fileTopbar.hidden = false;
  els.topFileName.textContent = uploadedOriginal;
  els.topFileMeta.textContent = els.fileMeta.textContent;
  startProxyFlow();
  saveSession();
}

async function importLocal(givenPath) {
  const raw = ((givenPath !== undefined ? givenPath : els.importPath.value) || "").trim();
  if (!raw) { els.importPath.focus(); return; }
  clearError();
  resetResults();
  resetAudioSelection();
  setWorking(true);
  els.uploadProgress.hidden = false;
  els.uploadFill.style.width = "100%";
  els.uploadPct.textContent = "…";
  els.uploadSpeed.textContent = "";
  els.fileChip.hidden = true;
  try {
    const response = await fetch("/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: raw }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    afterFileReady(data, data.original_name, data.size_bytes,
      `/media/${encodeURIComponent(data.filename)}`);
    els.importForm.hidden = true;
  } catch (err) {
    showError(err.message);
    els.uploadProgress.hidden = true;
  } finally {
    setWorking(false);
  }
}
/* ---------- sunucu dosya tarayıcı (yol yazmadan /import) ---------- */
const BROWSE_KEY = "precutter-browse-dir";

async function openBrowse() {
  els.browseModal.hidden = false;
  els.browseNote.hidden = true;
  let start = null;
  try { start = localStorage.getItem(BROWSE_KEY); } catch (e) { /* ignore */ }
  await browseDir(start);
}

function closeBrowse() {
  els.browseModal.hidden = true;
}

async function browseDir(path) {
  els.browseList.innerHTML = "";
  els.browseNote.hidden = true;
  try {
    const url = path ? `/browse?path=${encodeURIComponent(path)}` : "/browse";
    const response = await fetch(url);
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    renderBrowse(data);
    if (data.cwd) {
      try { localStorage.setItem(BROWSE_KEY, data.cwd); } catch (e) { /* ignore */ }
    }
  } catch (err) {
    els.browseNote.hidden = false;
    els.browseNote.textContent = err.message;
  }
}

function browseRow(label, meta, onClick) {
  const b = document.createElement("button");
  b.className = "browse-row";
  b.type = "button";
  const nm = document.createElement("span");
  nm.textContent = label;
  const mm = document.createElement("span");
  mm.className = "mono meta";
  mm.textContent = meta || "";
  b.appendChild(nm);
  b.appendChild(mm);
  b.addEventListener("click", onClick);
  els.browseList.appendChild(b);
}

function renderBrowse(data) {
  els.browsePath.textContent = data.cwd || t("browseRoots");
  if (!data.cwd) {
    const home = data.home;
    if (home) browseRow("~ (" + home + ")", "", () => browseDir(home));
    for (const r of data.roots || []) browseRow(r, "", () => browseDir(r));
    if (!(data.roots || []).length && !home) {
      els.browseNote.hidden = false;
      els.browseNote.textContent = t("browseEmpty");
    }
    return;
  }
  if (data.parent) browseRow(t("browseUp"), "", () => browseDir(data.parent));
  for (const d of data.dirs || []) {
    browseRow("📁 " + d.name, "", () => browseDir(d.path));
  }
  for (const f of data.files || []) {
    browseRow("🎬 " + f.name, fmtBytes(f.size_bytes), () => {
      closeBrowse();
      importLocal(f.path);
    });
  }
  if (!(data.dirs || []).length && !(data.files || []).length) {
    els.browseNote.hidden = false;
    els.browseNote.textContent = t("browseEmpty");
  }
}
/* ---------- preview proxy: hafif ses/video, hazır olunca tak ---------- */
function proxyUrls(status) {
  const audio = {};
  for (const [track, file] of Object.entries(status.audio || {})) {
    audio[track] = `/proxy-audio/${encodeURIComponent(uploadedName)}?track=${track}`;
  }
  return {
    audio,
    video: status.video
      ? `/proxy-video/${encodeURIComponent(uploadedName)}`
      : null,
  };
}

async function startProxyFlow() {
  if (!uploadedName) return;
  els.proxyNote.hidden = false;
  els.proxyNote.textContent = t("proxyPreparing").replace("{p}", "0");
  try {
    const st = await fetch(`/proxy/${encodeURIComponent(uploadedName)}`);
    if (st.ok) {
      const status = await st.json();
      if (status.ready && window.PrecutterPlayer) {
        window.PrecutterPlayer.setProxies(proxyUrls(status));
        els.proxyNote.textContent = t("proxyReady");
        setTimeout(() => { els.proxyNote.hidden = true; }, 3000);
        return;
      }
    }
  } catch (e) { /* job ile devam et */ }
  try {
    const response = await fetch("/proxy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: uploadedName }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const { job_id } = await response.json();
    await pollProxyJob(job_id);
  } catch (err) {
    els.proxyNote.hidden = true;
    if (window.PrecutterPlayer) window.PrecutterPlayer.proxyFailed();
  }
}

async function pollProxyJob(jobId) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    let job;
    try {
      const response = await fetch(`/jobs/${jobId}`);
      if (!response.ok) throw new Error(await readError(response));
      job = await response.json();
    } catch (err) {
      els.proxyNote.hidden = true;
      if (window.PrecutterPlayer) window.PrecutterPlayer.proxyFailed();
      break;
    }
    if (job.total) {
      const pct = Math.round((job.done / job.total) * 100);
      els.proxyNote.textContent = t("proxyPreparing").replace("{p}", pct);
    }
    // Ses proxy'leri biten izi hemen tak: video kodlanırken ses gelir.
    try {
      if (uploadedName && window.PrecutterPlayer) {
        const st = await fetch(`/proxy/${encodeURIComponent(uploadedName)}`);
        if (st.ok) window.PrecutterPlayer.noteProxyProgress(await st.json());
      }
    } catch (e) { /* next tick */ }
    if (job.status === "done") {
      if (window.PrecutterPlayer) {
        window.PrecutterPlayer.setProxies(proxyUrls(job.result || {}));
      }
      els.proxyNote.textContent = t("proxyReady");
      setTimeout(() => { els.proxyNote.hidden = true; }, 3000);
      break;
    }
    if (job.status === "error") {
      els.proxyNote.hidden = true;
      if (window.PrecutterPlayer) window.PrecutterPlayer.proxyFailed();
      break;
    }
  }
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
  resetAudioSelection();
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
      afterFileReady(data, file.name, file.size, null);
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
  els.playerBar.hidden = false;
}

function showFileChip(file, data, enrich = true) {
  els.uploadProgress.hidden = true;
  els.fileChip.hidden = false;
  els.fileName.textContent = data.original_name || file.name;
  const dur = data.duration_seconds != null ? fmtDur(data.duration_seconds) : "?";
  const trackInfo = data.audio_streams && data.audio_streams.length > 1
    ? ` · ${data.audio_streams.length} ${t("audioTracks")}`
    : "";
  els.fileMeta.textContent = `${fmtBytes(file.size)} · ${dur}${trackInfo}`;
  if (data.audio_streams && data.audio_streams.length) {
    setupAudioStreams(data.audio_streams, data.suggested_mic);
  }
  if (enrich) fetchAudioStreams();
  resetAudition();
  setWorking(false);
}

/* ---------- oturum kalıcılığı: yenilemede her şey geri gelir ---------- */
const SESSION_KEY = "precutter-session";

function saveSession() {
  if (!uploadedName) return;
  try {
    const ch = els.audioChannel ? els.audioChannel.value : "mix";
    localStorage.setItem(SESSION_KEY, JSON.stringify({
      file: uploadedName,
      original: uploadedOriginal,
      duration: uploadedDuration,
      size: uploadedSize,
      track: audioTrackIndex,
      channel: ch,
      fillerOn,
      subtitleOn,
      aiCut: aiCutOn,
      aiThreshold: els.aiThreshold ? Number(els.aiThreshold.value) : 30,
      analysis: lastAnalysis,
      detail: analysisDetail,
    }));
  } catch (e) { /* depolama yoksa sessiz */ }
}

function clearSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch (e) { /* ignore */ }
}

async function restoreSession() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(SESSION_KEY)); } catch (e) { return; }
  if (!s || !s.file) return;
  try {
    const pr = await fetch("/projects");
    if (!pr.ok) return;
    const items = (await pr.json()).projects || [];
    const found = items.find((p) => p.filename === s.file);
    if (!found) { clearSession(); return; }
    uploadedName = s.file;
    uploadedOriginal = s.original || s.file;
    uploadedDuration = s.duration != null ? s.duration : found.duration_seconds;
    uploadedSize = s.size != null ? s.size : found.size_bytes;
    if (s.track != null) { audioTrackIndex = s.track; userPickedTrack = true; }
    if (els.audioChannel && (s.channel === "0" || s.channel === "1" || s.channel === "mix")) {
      els.audioChannel.value = s.channel;
    }
    toggleFiller(!!s.fillerOn);
    toggleSubtitle(!!s.subtitleOn);
    toggleAICut(!!s.aiCut);
    if (s.aiThreshold && els.aiThreshold) {
      els.aiThreshold.value = s.aiThreshold;
      syncAiThreshold();
    }
    showFileChip(
      { name: uploadedOriginal, size: uploadedSize || 0 },
      { original_name: uploadedOriginal, duration_seconds: uploadedDuration },
      false,
    );
    await fetchAudioStreams();
    if (s.channel && els.audioChannel) els.audioChannel.value = s.channel;
    els.previewVideo.src = `/media/${encodeURIComponent(uploadedName)}`;
    els.previewVideo.hidden = false;
    els.previewPlaceholder.hidden = true;
    els.previewTag.textContent = uploadedOriginal;
    els.previewTag.hidden = false;
    els.settingsSub.textContent = uploadedOriginal;
    els.uploadCard.hidden = true;
    els.fileTopbar.hidden = false;
    els.topFileName.textContent = uploadedOriginal;
    els.topFileMeta.textContent = els.fileMeta.textContent;
    els.playerBar.hidden = false;
    startProxyFlow();
    if (s.analysis && s.analysis.segments && s.analysis.segments.length) {
      applyAnalysisResult(s.analysis);
      setAnalysisState("done", s.detail || "");
    }
    saveSession();
    // Player modülü geç yüklenebilir: analiz varsa geç de olsa doldur.
    setTimeout(ensurePlayerLoaded, 2000);
  } catch (e) { /* temiz başlangıç */ }
}

function ensurePlayerLoaded() {
  try {
    const ed = window.PrecutterPlayer;
    if (!ed || !lastSegments || !lastSegments.length) return;
    ed.loadAnalysis({
      segments: lastSegments,
      cuts: lastCuts,
      music: lastMusic,
      highlights: (lastAnalysis && lastAnalysis.highlights) || [],
      duration: uploadedDuration || 0,
      fps: lastFps,
      summary: lastSummary,
      filename: uploadedName,
      tracks: audioStreams,
      micIndex: audioTrackIndex,
    });
    if (ed.setAudioTracks && audioStreams && audioStreams.length) {
      ed.setAudioTracks(audioStreams, audioTrackIndex, uploadedName);
    }
  } catch (e) { /* ignore */ }
}

function removeFile() {
  uploadedName = null;
  uploadedOriginal = null;
  uploadedDuration = null;
  uploadedSize = null;
  fillerFetchedFor = null;
  userPickedTrack = false;
  clearSession();
  if (els.fillerSwitch.classList.contains("on")) toggleFiller(false);
  if (els.aiCutSwitch.classList.contains("on")) toggleAICut(false);
  els.playerBar.hidden = true;
  els.fileChip.hidden = true;
  els.uploadProgress.hidden = true;
  els.previewVideo.removeAttribute("src");
  els.previewVideo.hidden = true;
  els.previewPlaceholder.hidden = false;
  els.previewTag.hidden = true;
  els.fileInput.value = "";
  els.settingsSub.textContent = "-";
  els.uploadCard.hidden = false;
  els.fileTopbar.hidden = true;
  els.playerBar.hidden = true;
  resetAudition();
  resetResults();
  setWorking(false);
}

function resetResults() {
  els.statTotal.textContent = "-";
  els.statKept.textContent = "-";
  els.statCut.textContent = "-";
  els.summaryLine.hidden = true;
  els.downloadLink.hidden = true;
  els.fillerInfo.hidden = true;
  els.outputMeta.hidden = true;
  lastEstimate = null;
  lastSummary = null;
  lastSegments = null;
  lastAnalysis = null;
  lastCuts = [];
  lastMusic = [];
  hasTranscript = false;
  transcriptWords = 0;
  els.srtBtn.disabled = true;
  els.aiInfo.hidden = true;
  els.aiContent.textContent = t("aiContentNone");
  els.proxyNote.hidden = true;
  stopRenderCountdown();
  refreshExportNote();
  setAnalysisState("idle", "");
  if (window.PrecutterPlayer) window.PrecutterPlayer.reset();
  setWorking(false);
}

function resetAudioSelection() {
  audioTrackIndex = 0;
  audioStreams = [];
  userPickedTrack = false;
  els.audioTrack.innerHTML = "";
  els.noAudioHelp.hidden = false;
  if (els.channelField) els.channelField.hidden = true;
  resetAudition();
}

/* legacy canvas timeline kaldirildi: Peaks.js view-only player. */

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

/* ---------- analyze (tek analiz, job tabanlı), sonra kullanıcı isterse render ----------
   (view-only: currentSegments her zaman son analizdir) ---------- */
function stageLabel(job, stageKey) {
  // "sırada" gizemi bitsin: slotu kimin tuttuğunu yaz.
  if (job && job.stage === "queued" && job.blocked_by && job.blocked_by.kind) {
    const kindKey = {
      analyze: "stageAnalyze", transcribe: "stageTranscribe",
      render: "stageRender", proxy: "stageProxy",
    }[job.blocked_by.kind];
    if (kindKey) return `${t("stageQueued")} · ${t(kindKey)}`;
  }
  return t(stageKey);
}
function currentSegments() {
  return lastSegments;
}

function applyAnalysisResult(data) {
  lastAnalysis = data;
  lastSegments = data.segments;
  lastCuts = data.cuts || [];
  lastMusic = data.music || [];
  lastFps = data.fps || 30;
  showSummary(data.summary);
  els.downloadLink.hidden = true;
  els.outputMeta.hidden = true;
  if (window.PrecutterPlayer) {
    window.PrecutterPlayer.loadAnalysis({
      segments: data.segments,
      cuts: data.cuts || [],
      music: data.music || [],
      highlights: data.highlights || [],
      duration: data.duration,
      fps: data.fps || 30,
      summary: data.summary,
      filename: uploadedName,
      tracks: audioStreams,
      micIndex: audioTrackIndex,
    });
  }
  const tr = data.transcript || {};
  hasTranscript = !!tr.available;
  transcriptWords = tr.word_count || 0;
  if (hasTranscript) {
    fillerFetchedFor = uploadedName;
    const n = tr.filler_count || 0;
    els.fillerInfo.hidden = false;
    if (fillerOn && n > 0) {
      els.fillerInfo.textContent =
        t("fillerFound").replace("{n}", n).replace("{p}", ((tr.filler_ratio || 0) * 100).toFixed(1));
    } else if (subtitleOn) {
      els.fillerInfo.textContent = t("subtitleReady").replace("{n}", transcriptWords);
    } else {
      els.fillerInfo.hidden = true;
    }
  } else {
    hasTranscript = false;
    transcriptWords = 0;
    els.fillerInfo.hidden = true;
  }
  const summary = data.summary || {};
  if (summary.ai_cut_count > 0) {
    els.aiInfo.hidden = false;
    els.aiInfo.textContent = t("aiCutFound")
      .replace("{n}", summary.ai_cut_count)
      .replace("{src}", summary.ai_source || "llm");
  } else {
    els.aiInfo.hidden = true;
  }
  const content = data.content || {};
  els.aiContent.textContent = content.label || t("aiContentNone");
  setWorking(false);
  saveSession();
}

async function analyze() {
  if (!uploadedName) { showError(t("noFile")); return false; }
  clearError();
  setWorking(true);
  els.analyzeBtn.textContent = "...";
  els.renderProgress.hidden = false;
  els.renderFill.style.width = "0%";
  els.renderPct.textContent = "0%";
  const prevState = analysisState;
  const prevDetail = analysisDetail;
  setAnalysisState("working");
  try {
    const response = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params()),
    });
    if (!response.ok) throw new Error(await readError(response));
    const { job_id } = await response.json();
    return await pollAnalyzeJob(job_id, prevState, prevDetail);
  } catch (err) {
    showError(err.message);
    // Başarısız analiz rozeti "Analiz ediliyor"da takılı bırakmamalı.
    setAnalysisState(prevState === "working" ? "idle" : prevState, prevDetail);
    els.renderProgress.hidden = true;
    els.analyzeBtn.textContent = t("analyzeBtn");
    setWorking(false);
    return false;
  }
}

async function pollAnalyzeJob(jobId, prevState, prevDetail) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 1200));
    let job;
    try {
      const response = await fetch(`/jobs/${jobId}`);
      if (!response.ok) throw new Error(await readError(response));
      job = await response.json();
    } catch (err) {
      showError(err.message);
      els.renderProgress.hidden = true;
      els.analyzeBtn.textContent = t("analyzeBtn");
      setWorking(false);
      return false;
    }
    const stageKey = {
      queued: "stageQueued", silence: "stageSilence",
      transcribe: "stageTranscribe", analyze: "stageAnalyze",
      events: "stageEvents", ai: "stageAI",
    }[job.stage] || "stageAnalyze";
    els.renderStage.textContent = stageLabel(job, stageKey);
    if (job.stage === "transcribe" && job.total) {
      const pct = (job.done / job.total) * 100;
      els.renderFill.style.width = `${pct.toFixed(1)}%`;
      els.renderPct.textContent = t("transcriptProgress").replace("{p}", pct.toFixed(0));
    } else if (job.stage === "silence") {
      els.renderFill.style.width = "8%";
      els.renderPct.textContent = t("stageSilence") + "…";
    } else if (job.total) {
      const pct = (job.done / job.total) * 100;
      els.renderFill.style.width = `${pct.toFixed(1)}%`;
      els.renderPct.textContent = `${pct.toFixed(0)}%`;
    }
    if (job.status === "done") {
      els.renderFill.style.width = "100%";
      els.renderPct.textContent = "100%";
      setTimeout(() => { els.renderProgress.hidden = true; }, 2500);
      applyAnalysisResult(job.result || {});
      const p = params();
      setAnalysisState("done", `${fmtClock(new Date())} · ${p.threshold_db}dB`);
      els.analyzeBtn.textContent = t("analyzeBtn");
      return true;
    }
    if (job.status === "error") {
      showError(job.error || t("errUpload"));
      els.renderProgress.hidden = true;
      setAnalysisState(prevState === "working" ? "idle" : prevState, prevDetail);
      els.analyzeBtn.textContent = t("analyzeBtn");
      setWorking(false);
      return false;
    }
  }
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
      body: JSON.stringify(params(true)),
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
    if (job.stage) {
      const key = {
        render: "stageRender", analyze: "stageAnalyze", queued: "stageQueued",
        silence: "stageSilence", transcribe: "stageTranscribe",
        events: "stageEvents", ai: "stageAI",
      }[job.stage] || "stageAnalyze";
      els.renderStage.textContent = stageLabel(job, key);
    }
    if (job.total) {
      const pct = (job.done / job.total) * 100;
      els.renderFill.style.width = `${pct.toFixed(1)}%`;
      els.renderPct.textContent = `${pct.toFixed(0)}%`;
    }
    if (job.status === "done") {
      els.renderFill.style.width = "100%";
      els.renderPct.textContent = "100%";
      lastEstimate = estimateSeconds(job.summary);
      // lastSegments korunur: render sonrası SRT/JSON indirilebilmeli.
      showSummary(job.summary);
      els.downloadLink.href = job.download_url;
      els.downloadLink.hidden = false;
      if (window.PrecutterPlayer) window.PrecutterPlayer.setRenderedUrl(job.download_url);
      els.previewTag.textContent = t("previewResult");
      els.previewTag.hidden = false;
      if (job.output_audio_tracks != null) {
        els.outputMeta.textContent = t("outputTracks").replace("{n}", job.output_audio_tracks);
        els.outputMeta.hidden = false;
      }
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

/* ---------- rendered mode: player owns the source (no manual toggle) ---------- */

async function fetchFillers() {
  // Çalışan bir transkript varken tekrar tetiklenirse ikinci Whisper
  // başlamasın; mevcut döngü zaten yüzdesiyle güncelliyor.
  if (!uploadedName || fillerJobRunning || fillerFetchedFor === uploadedName) return;
  fillerJobRunning = true;
  els.fillerInfo.hidden = false;
  els.fillerInfo.textContent = t("fillerWorking");
  try {
    const response = await fetch("/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: uploadedName, remove_fillers: true, audio_track: audioTrackIndex }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const { job_id } = await response.json();
    await pollTranscribeJob(job_id);
  } catch (err) {
    els.fillerInfo.textContent = err.message;
  } finally {
    fillerJobRunning = false;
  }
}

async function pollTranscribeJob(jobId) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    let job;
    try {
      const response = await fetch(`/jobs/${jobId}`);
      if (!response.ok) throw new Error(await readError(response));
      job = await response.json();
    } catch (err) {
      els.fillerInfo.textContent = err.message;
      break;
    }
    if (job.total) {
      const pct = Math.round((job.done / job.total) * 100);
      els.fillerInfo.textContent = t("transcriptProgress").replace("{p}", pct);
    } else if (job.stage === "queued") {
      els.fillerInfo.textContent = t("fillerWorking") + " " + t("stageQueued") + "…";
    }
    if (job.status === "done") {
      const data = job.result || {};
      fillerFetchedFor = uploadedName;
      hasTranscript = true;
      transcriptWords = (data.words || []).length;
      setWorking(false);
      const n = (data.fillers || []).length;
      els.fillerInfo.hidden = false;
      els.fillerInfo.textContent =
        n > 0 && fillerOn
          ? t("fillerFound").replace("{n}", n).replace("{p}", ((data.filler_ratio || 0) * 100).toFixed(1))
          : t("subtitleReady").replace("{n}", transcriptWords);
      break;
    }
    if (job.status === "error") {
      els.fillerInfo.textContent = job.error || t("errUpload");
      break;
    }
  }
}

function toggleFiller(force) {
  fillerOn = force !== undefined ? force : !els.fillerSwitch.classList.contains("on");
  els.fillerSwitch.classList.toggle("on", fillerOn);
  els.fillerSwitch.setAttribute("aria-checked", String(fillerOn));
  if (!fillerOn) els.fillerInfo.hidden = true;
  // Dolgu, tek analizin seçeneğidir: ayrı transkript koşmaz, sadece sonuç bayatlar.
  markStale();
  saveSession();
}

function toggleSubtitle(force) {
  subtitleOn = force !== undefined ? force : !els.subtitleSwitch.classList.contains("on");
  els.subtitleSwitch.classList.toggle("on", subtitleOn);
  els.subtitleSwitch.setAttribute("aria-checked", String(subtitleOn));
  // Altyazı da tek analizin seçeneğidir: transkript analizle birlikte gelir.
  markStale();
  saveSession();
}

function toggleAICut(force) {
  aiCutOn = force !== undefined ? force : !els.aiCutSwitch.classList.contains("on");
  els.aiCutSwitch.classList.toggle("on", aiCutOn);
  els.aiCutSwitch.setAttribute("aria-checked", String(aiCutOn));
  // AI kesim de tek analizin seçeneğidir.
  markStale();
  saveSession();
}

function syncAiThreshold() {
  if (els.aiThresholdValue) els.aiThresholdValue.textContent = `${els.aiThreshold.value}`;
}

/* ---------- AI sohbet ---------- */
function appendChat(role, text) {
  const div = document.createElement("div");
  div.className = "chat-msg" + (role === "user" ? " user" : "");
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? t("chatYou") : "PRE.AI";
  const body = document.createElement("span");
  body.className = "txt";
  body.textContent = text;
  div.appendChild(who);
  div.appendChild(body);
  els.chatLog.appendChild(div);
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
  return div;
}

async function sendChat() {
  const msg = (els.chatInput.value || "").trim();
  if (!msg) return;
  if (!uploadedName) { showError(t("chatNeedFile")); return; }
  clearError();
  els.chatInput.value = "";
  appendChat("user", msg);
  chatHistory.push({ role: "user", content: msg });
  const typing = appendChat("assistant", t("chatTyping"));
  typing.classList.add("typing");
  els.chatSend.disabled = true;
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: uploadedName,
        message: msg,
        history: chatHistory.slice(-6),
        audio_track: audioTrackIndex,
      }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    typing.querySelector(".txt").textContent = data.reply || "-";
    typing.classList.remove("typing");
    chatHistory.push({ role: "assistant", content: data.reply || "" });
  } catch (err) {
    typing.querySelector(".txt").textContent = err.message;
    typing.classList.remove("typing");
  } finally {
    els.chatSend.disabled = !uploadedName;
  }
}

async function downloadSrt() {
  const segs = lastSegments;
  if (!uploadedName || !segs) return;
  clearError();
  setWorking(true);
  try {
    let response = await fetch("/srt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: uploadedName,
        segments: segs,
        audio_track: audioTrackIndex,
      }),
    });
    if (response.status === 409) {
      // Transkript yok: analizden sonra opsiyonel altyazı — şimdi üret, sonra indir.
      await fetchFillers();
      if (!hasTranscript) throw new Error(t("srtNoTranscript"));
      response = await fetch("/srt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: uploadedName,
          segments: lastSegments || segs,
          audio_track: audioTrackIndex,
        }),
      });
    }
    if (!response.ok) throw new Error(await readError(response));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(uploadedOriginal || uploadedName).replace(/\.[^.]+$/, "")}_cut.srt`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err.message);
  } finally {
    setWorking(false);
  }
}

function downloadJson() {
  const segs = lastSegments;
  if (!lastSummary || !segs) return;
  const payload = {
    source: uploadedOriginal || uploadedName,
    params: params(true),
    segments: segs,
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
function applyPreset(name, persist = true) {
  const p = PRESETS[name];
  if (!p) return;
  activePreset = name;
  els.threshold.value = p.threshold;
  els.minSilence.value = p.minSilence;
  els.paddingPre.value = p.paddingPre;
  els.paddingPost.value = p.paddingPost;
  document.querySelectorAll(".preset-chip").forEach((c) =>
    c.classList.toggle("active", c.dataset.preset === name)
  );
  syncSliders();
  markStale();
  if (persist) {
    fetch("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preset: name,
        threshold_db: p.threshold,
        min_silence: p.minSilence,
        padding_pre: p.paddingPre,
        padding_post: p.paddingPost,
      }),
    }).catch(() => {});
  }
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
    // Önizleme dosyası sunucuda hazırlanır (ilk seferde biraz sürer), sonra oynatılır.
    // Seçili kanal solo + mono indirgenir: tek kanaldaki mikrofon ortada duyulur.
    const ch = els.audioChannel ? els.audioChannel.value : "mix";
    const url = `/preview-audio/${encodeURIComponent(uploadedName)}?track=${audioTrackIndex}&channel=${ch}`;
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

/* ---------- settings modal ---------- */
function syncSettingsLabels() {
  els.setThresholdVal.textContent = `${els.setThreshold.value} dB`;
  els.setMinSilenceVal.textContent = `${Number(els.setMinSilence.value).toFixed(1)} ${t("secShort")}`;
  els.setPaddingPreVal.textContent = `${Math.round(Number(els.setPaddingPre.value) * 1000)} ms`;
  els.setPaddingPostVal.textContent = `${Math.round(Number(els.setPaddingPost.value) * 1000)} ms`;
  els.setMaxUploadVal.textContent = `${els.setMaxUpload.value} GB`;
  if (els.setAiThresholdVal && els.setAiThreshold) {
    els.setAiThresholdVal.textContent = `${els.setAiThreshold.value}`;
  }
}

function applySettingsToSliders(s) {
  els.threshold.value = s.threshold_db;
  els.minSilence.value = s.min_silence;
  els.paddingPre.value = s.padding_pre;
  els.paddingPost.value = s.padding_post;
  if (s.ai_threshold != null && els.aiThreshold) {
    els.aiThreshold.value = s.ai_threshold;
    syncAiThreshold();
  }
  syncSliders();
}

async function openSettings() {
  els.settingsModal.hidden = false;
  els.settingsNote.hidden = true;
  syncSettingsLabels();
  refreshDoctor();
  try {
    const response = await fetch("/settings");
    if (!response.ok) throw new Error(await readError(response));
    const s = await response.json();
    els.setThreshold.value = s.threshold_db;
    els.setMinSilence.value = s.min_silence;
    els.setPaddingPre.value = s.padding_pre;
    els.setPaddingPost.value = s.padding_post;
    els.setWhisper.value = s.whisper_model;
    els.setEncoder.value = s.encoder;
    els.setQuality.value = s.quality;
    els.setOutputAudio.value = s.output_audio;
    els.setMaxUpload.value = s.max_upload_gb;
    if (els.setOllama && s.ollama_host) els.setOllama.value = s.ollama_host;
    if (els.setAiModel && s.ai_model) els.setAiModel.value = s.ai_model;
    if (els.setAiThreshold && s.ai_threshold != null) {
      els.setAiThreshold.value = s.ai_threshold;
      if (els.aiThreshold) {
        els.aiThreshold.value = s.ai_threshold;
        syncAiThreshold();
      }
    }
    if (els.setPreviewVideo) els.setPreviewVideo.checked = !!s.preview_video;
    syncSettingsLabels();
  } catch (err) {
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = err.message;
  }
  refreshStorage();
}

async function refreshDoctor() {
  els.doctorBox.textContent = t("doctorLoading");
  try {
    const response = await fetch("/doctor");
    if (!response.ok) throw new Error(await readError(response));
    const d = await response.json();
    const row = (label, value, good) =>
      `<div>${label}: <span class="${good ? "b" : "bad"}">${value}</span></div>`;
    els.doctorBox.innerHTML =
      row("ffmpeg", d.ffmpeg_version || "—", d.ffmpeg) +
      row(t("encoderPref"), `${d.encoder || "—"}${d.nvenc ? " (NVENC)" : ""}`, d.ffmpeg) +
      row("Whisper", d.whisper_device === "cuda"
        ? `GPU${d.gpu_name ? " · " + d.gpu_name : ""}`
        : (d.whisper_device || (d.whisper ? "CPU" : "—")),
        d.whisper_device === "cuda" || !d.whisper) +
      row(t("freeDisk"), `${d.free_disk_gb != null ? d.free_disk_gb + " GB" : "—"}`, true) +
      row("CPU", d.cpu_count != null ? d.cpu_count : "—", true);
  } catch (err) {
    els.doctorBox.textContent = err.message;
  }
}

function closeSettings() {
  els.settingsModal.hidden = true;
}

async function saveSettings() {
  els.settingsNote.hidden = true;
  const patch = {
    threshold_db: Number(els.setThreshold.value),
    min_silence: Number(els.setMinSilence.value),
    padding_pre: Number(els.setPaddingPre.value),
    padding_post: Number(els.setPaddingPost.value),
    whisper_model: els.setWhisper.value,
    encoder: els.setEncoder.value,
    quality: els.setQuality.value,
    output_audio: els.setOutputAudio.value,
    max_upload_gb: Number(els.setMaxUpload.value),
    ollama_host: els.setOllama.value.trim(),
    ai_model: els.setAiModel.value.trim(),
    ai_threshold: Number(els.setAiThreshold.value),
    preview_video: !!(els.setPreviewVideo && els.setPreviewVideo.checked),
  };
  try {
    const response = await fetch("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!response.ok) throw new Error(await readError(response));
    const s = await response.json();
    applySettingsToSliders(s);
    if (s.max_upload_gb) {
      LIMITS.max_upload_bytes = s.max_upload_gb * 1024 ** 3;
      updateDropHint();
    }
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = t("settingsSaved");
  } catch (err) {
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = err.message;
  }
}

async function refreshStorage() {
  els.storageList.innerHTML = "";
  els.storageTotal.textContent = "";
  try {
    const response = await fetch("/projects");
    if (!response.ok) return;
    const data = await response.json();
    const items = data.projects || [];
    const total = items.reduce((a, p) => a + (p.size_bytes || 0), 0);
    els.storageTotal.textContent = `· ${fmtBytes(total)}`;
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "storage-empty";
      empty.textContent = t("storageEmpty");
      els.storageList.appendChild(empty);
      return;
    }
    for (const p of items) {
      const row = document.createElement("div");
      row.className = "storage-item";
      const info = document.createElement("div");
      const nm = document.createElement("div");
      nm.textContent = p.filename;
      const meta = document.createElement("div");
      meta.className = "mono";
      meta.textContent = `${fmtBytes(p.size_bytes)} · ${fmtDur(p.duration_seconds)}`;
      info.appendChild(nm);
      info.appendChild(meta);
      const del = document.createElement("button");
      del.className = "chip-remove";
      del.textContent = "×";
      del.addEventListener("click", () => deleteUpload(p.filename));
      row.appendChild(info);
      row.appendChild(del);
      els.storageList.appendChild(row);
    }
  } catch (e) { /* sessiz */ }
}

async function deleteUpload(filename) {
  try {
    const response = await fetch(`/uploads/${encodeURIComponent(filename)}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = t("freedBytes").replace("{x}", fmtBytes(data.freed_bytes));
    if (filename === uploadedName) removeFile();
    refreshStorage();
  } catch (err) {
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = err.message;
  }
}

async function clearCache() {
  try {
    const response = await fetch("/storage/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "cache" }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = t("freedBytes").replace("{x}", fmtBytes(data.freed_bytes));
    refreshStorage();
  } catch (err) {
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = err.message;
  }
}

async function clearAll() {
  if (!confirm(t("confirmClearAll"))) return;
  try {
    const response = await fetch("/storage/clear", { method: "POST" });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = t("freedBytes").replace("{x}", fmtBytes(data.freed_bytes));
    removeFile();
    refreshStorage();
  } catch (err) {
    els.settingsNote.hidden = false;
    els.settingsNote.textContent = err.message;
  }
}

/* ---------- events ---------- */
els.fileInput.addEventListener("change", (e) => uploadFile(e.target.files[0]));
els.navSettings.addEventListener("click", openSettings);
els.navSettings.addEventListener("keydown", (e) => {
  if (e.key === " " || e.key === "Enter") { e.preventDefault(); openSettings(); }
});
els.settingsClose.addEventListener("click", closeSettings);
els.settingsCancel.addEventListener("click", closeSettings);
els.settingsSave.addEventListener("click", saveSettings);
els.clearCacheBtn.addEventListener("click", clearCache);
els.clearAllBtn.addEventListener("click", clearAll);
els.settingsModal.addEventListener("click", (e) => {
  if (e.target === els.settingsModal) closeSettings();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !els.settingsModal.hidden) closeSettings();
  if (e.key === "Escape" && els.browseModal && !els.browseModal.hidden) closeBrowse();
});
[els.setThreshold, els.setMinSilence, els.setPaddingPre, els.setPaddingPost, els.setMaxUpload, els.setAiThreshold].forEach((s) =>
  s.addEventListener("input", syncSettingsLabels)
);
els.fileRemove.addEventListener("click", removeFile);
els.changeFileBtn.addEventListener("click", removeFile);
els.importToggle.addEventListener("click", () => {
  els.importForm.hidden = !els.importForm.hidden;
  if (!els.importForm.hidden) els.importPath.focus();
});
els.importBtn.addEventListener("click", () => importLocal());
els.browseBtn.addEventListener("click", openBrowse);
els.browseClose.addEventListener("click", closeBrowse);
els.browseModal.addEventListener("click", (e) => {
  if (e.target === els.browseModal) closeBrowse();
});
els.importPath.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); importLocal(); }
});

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

[els.threshold, els.minSilence, els.paddingPre, els.paddingPost].forEach((slider) =>
  slider.addEventListener("input", () => {
    syncSliders();
    document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
    markStale();
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
els.subtitleSwitch.addEventListener("click", () => toggleSubtitle());
els.subtitleSwitch.addEventListener("keydown", (e) => {
  if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggleSubtitle(); }
});
els.aiCutSwitch.addEventListener("click", () => toggleAICut());
els.aiCutSwitch.addEventListener("keydown", (e) => {
  if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggleAICut(); }
});
els.aiThreshold.addEventListener("input", () => {
  syncAiThreshold();
  markStale();
  saveSession();
});
els.chatSend.addEventListener("click", sendChat);
els.chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); sendChat(); }
});

els.audioTrack.addEventListener("change", () => {
  audioTrackIndex = Number(els.audioTrack.value) || 0;
  userPickedTrack = true;
  fillerFetchedFor = null;
  updateChannelField();
  resetAudition();
  if (lastSummary) resetResults();
  saveSession();
});
els.audioChannel.addEventListener("change", () => {
  if (lastSummary) resetResults();
  saveSession();
});
els.auditionBtn.addEventListener("click", audition);

els.analyzeBtn.addEventListener("click", analyze);
els.renderBtn.addEventListener("click", render);
els.jsonBtn.addEventListener("click", downloadJson);
els.srtBtn.addEventListener("click", downloadSrt);
els.langTr.addEventListener("click", () => setLang("tr"));
els.langEn.addEventListener("click", () => setLang("en"));

/* ---------- init ---------- */
async function init() {
  let savedPreset = "game";
  try {
    const response = await fetch("/health");
    if (response.ok) {
      const data = await response.json();
      if (data.limits) LIMITS = data.limits;
    }
  } catch (e) { /* varsayılan limitlerle devam */ }
  try {
    const sres = await fetch("/settings");
    if (sres.ok) {
      const s = await sres.json();
      if (s.max_upload_gb) {
        LIMITS.max_upload_bytes = s.max_upload_gb * 1024 ** 3;
      }
      if (typeof s.preset === "string") savedPreset = s.preset;
    }
  } catch (e) { /* varsayılan ayarlarla devam */ }
  // Önce sunucu ayarları, sonra kayıtlı preset: chip + slider hep uyumlu.
  applyPreset(savedPreset, false);
  applyLang();
  syncAiThreshold();
  resetAudition();
  setWorking(false);
  // Yenilemede dosya + analiz geri gelsin.
  await restoreSession();
}

init();
