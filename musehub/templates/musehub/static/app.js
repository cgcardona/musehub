"use strict";
(() => {
  // musehub/templates/musehub/static/js/musehub.ts
  var API = "/api/v1";
  function getToken() {
    return localStorage.getItem("musehub_token") ?? "";
  }
  function setToken(t) {
    localStorage.setItem("musehub_token", t);
  }
  function clearToken() {
    localStorage.removeItem("musehub_token");
  }
  function authHeaders() {
    const t = getToken();
    return t ? { Authorization: "Bearer " + t, "Content-Type": "application/json" } : {};
  }
  async function apiFetch(path, opts = {}) {
    const res = await fetch(API + path, {
      ...opts,
      headers: { ...authHeaders(), ...opts.headers ?? {} }
    });
    if (res.status === 401 || res.status === 403) {
      showTokenForm("Session expired or invalid token \u2014 please re-enter your JWT.");
      throw new Error("auth");
    }
    if (!res.ok) {
      const body = await res.text();
      throw new Error(res.status + ": " + body);
    }
    return res.json();
  }
  function showTokenForm(msg) {
    const tf = document.getElementById("token-form");
    const content = document.getElementById("content");
    if (tf) tf.style.display = "block";
    if (content) content.innerHTML = "";
    if (msg) {
      const msgEl = document.getElementById("token-msg");
      if (msgEl) msgEl.textContent = msg;
    }
  }
  function saveToken() {
    const input = document.getElementById("token-input");
    const t = input?.value.trim() ?? "";
    if (t) {
      setToken(t);
      location.reload();
    }
  }
  function fmtDate(iso) {
    if (!iso) return "--";
    const d = new Date(iso);
    return d.toLocaleString(void 0, { dateStyle: "medium", timeStyle: "short" });
  }
  function fmtRelative(iso) {
    if (!iso) return "--";
    const diff = (Date.now() - new Date(iso).getTime()) / 1e3;
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    if (diff < 604800) return Math.floor(diff / 86400) + "d ago";
    return fmtDate(iso);
  }
  function shortSha(sha) {
    return sha ? sha.substring(0, 8) : "--";
  }
  function fmtDuration(seconds) {
    if (!seconds || isNaN(seconds)) return "--";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor(seconds % 3600 / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }
  function fmtSeconds(t) {
    if (isNaN(t)) return "0:00";
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  }
  function escHtml(s) {
    if (!s) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  async function initRepoNav(repoId) {
    try {
      const repo = await fetch(API + "/repos/" + repoId, { headers: authHeaders() }).then((r) => r.ok ? r.json() : null).catch(() => null);
      if (repo) {
        const badge = document.getElementById("nav-visibility-badge");
        if (badge) {
          badge.textContent = repo.visibility;
          badge.className = "badge repo-visibility-badge badge-" + (repo.visibility === "public" ? "clean" : "neutral");
        }
        const keyEl = document.getElementById("nav-key");
        if (keyEl && repo.keySignature) {
          keyEl.textContent = "\u2669 " + repo.keySignature;
          keyEl.style.display = "";
        }
        const bpmEl = document.getElementById("nav-bpm");
        if (bpmEl && repo.tempoBpm) {
          bpmEl.textContent = repo.tempoBpm + " BPM";
          bpmEl.style.display = "";
        }
        const tagsEl = document.getElementById("nav-tags");
        if (tagsEl && repo.tags && repo.tags.length > 0) {
          tagsEl.innerHTML = repo.tags.map((t) => '<span class="nav-meta-tag">' + escHtml(t) + "</span>").join("");
        }
      }
      if (getToken()) {
        const starBtn = document.getElementById("nav-star-btn");
        if (starBtn) starBtn.style.display = "";
      }
      void Promise.all([
        fetch(API + "/repos/" + repoId + "/pull-requests?state=open", { headers: authHeaders() }).then((r) => r.ok ? r.json() : { pull_requests: [] }).catch(() => ({ pull_requests: [] })),
        fetch(API + "/repos/" + repoId + "/issues?state=open", { headers: authHeaders() }).then((r) => r.ok ? r.json() : { issues: [] }).catch(() => ({ issues: [] }))
      ]).then(([prData, issueData]) => {
        const prCount = (prData.pull_requests ?? []).length;
        const issueCount = (issueData.issues ?? []).length;
        const prBadge = document.getElementById("nav-pr-count");
        if (prBadge && prCount > 0) {
          prBadge.textContent = String(prCount);
          prBadge.style.display = "";
        }
        const issueBadge = document.getElementById("nav-issue-count");
        if (issueBadge && issueCount > 0) {
          issueBadge.textContent = String(issueCount);
          issueBadge.style.display = "";
        }
      });
    } catch {
    }
  }
  async function toggleStar() {
    const icon = document.getElementById("nav-star-icon");
    if (icon) icon.textContent = icon.textContent === "\u2606" ? "\u2605" : "\u2606";
  }
  var _player = { playing: false };
  function _audioEl() {
    return document.getElementById("player-audio");
  }
  function _playerBar() {
    return document.getElementById("audio-player");
  }
  async function _fetchBlobUrl(url) {
    const res = await fetch(url, {
      headers: { Authorization: "Bearer " + getToken() }
    });
    if (!res.ok) throw new Error(String(res.status));
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  }
  async function queueAudio(url, title, repoName) {
    const bar = _playerBar();
    const audio = _audioEl();
    if (!bar || !audio) return;
    bar.style.display = "flex";
    document.body.classList.add("player-open");
    const t = document.getElementById("player-title");
    const r = document.getElementById("player-repo");
    if (t) t.textContent = title || "Now Playing";
    if (r) r.textContent = repoName || "";
    try {
      const blobUrl = await _fetchBlobUrl(url);
      const extAudio = audio;
      if (extAudio._blobUrl) URL.revokeObjectURL(extAudio._blobUrl);
      extAudio._blobUrl = blobUrl;
      audio.src = blobUrl;
    } catch {
      audio.src = url;
    }
    audio.load();
    void audio.play().catch(() => {
    });
    _player.playing = true;
    _updatePlayBtn();
  }
  function togglePlay() {
    const audio = _audioEl();
    if (!audio?.src) return;
    if (_player.playing) {
      audio.pause();
      _player.playing = false;
    } else {
      void audio.play().catch(() => {
      });
      _player.playing = true;
    }
    _updatePlayBtn();
  }
  function seekAudio(value) {
    const audio = _audioEl();
    if (!audio || !audio.duration) return;
    audio.currentTime = value / 100 * audio.duration;
  }
  function closePlayer() {
    const bar = _playerBar();
    const audio = _audioEl();
    if (bar) bar.style.display = "none";
    document.body.classList.remove("player-open");
    if (audio) {
      audio.pause();
      const extAudio = audio;
      if (extAudio._blobUrl) {
        URL.revokeObjectURL(extAudio._blobUrl);
        extAudio._blobUrl = void 0;
      }
      audio.src = "";
    }
    _player.playing = false;
    _updatePlayBtn();
  }
  async function downloadArtifact(url, filename) {
    const res = await fetch(url, {
      headers: { Authorization: "Bearer " + getToken() }
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(blobUrl);
  }
  function onTimeUpdate() {
    const audio = _audioEl();
    if (!audio?.duration) return;
    const pct = audio.currentTime / audio.duration * 100;
    const seek = document.getElementById("player-seek");
    const cur = document.getElementById("player-current");
    if (seek) seek.value = String(pct);
    if (cur) cur.textContent = fmtSeconds(audio.currentTime);
  }
  function onMetadata() {
    const audio = _audioEl();
    const dur = document.getElementById("player-duration");
    if (audio && dur) dur.textContent = fmtSeconds(audio.duration);
  }
  function onAudioEnded() {
    _player.playing = false;
    _updatePlayBtn();
    const seek = document.getElementById("player-seek");
    if (seek) seek.value = "0";
    const cur = document.getElementById("player-current");
    if (cur) cur.textContent = "0:00";
  }
  function _updatePlayBtn() {
    const btn = document.getElementById("player-toggle");
    if (btn) btn.innerHTML = _player.playing ? "&#9646;&#9646;" : "&#9654;";
  }
  var _COMMIT_TYPES = {
    feat: { label: "feat", color: "var(--color-success)" },
    fix: { label: "fix", color: "var(--color-danger)" },
    refactor: { label: "refactor", color: "var(--color-accent)" },
    style: { label: "style", color: "var(--color-purple)" },
    docs: { label: "docs", color: "var(--text-muted)" },
    chore: { label: "chore", color: "var(--color-neutral)" },
    init: { label: "init", color: "var(--color-warning)" },
    perf: { label: "perf", color: "var(--color-orange)" }
  };
  function parseCommitMessage(msg) {
    if (!msg) return { type: null, scope: null, subject: msg ?? "" };
    const m = msg.match(/^(\w+)(?:\(([^)]+)\))?:\s*(.*)/s);
    if (!m) return { type: null, scope: null, subject: msg };
    return { type: m[1].toLowerCase(), scope: m[2] ?? null, subject: m[3] };
  }
  function commitTypeBadge(type) {
    if (!type) return "";
    const t = _COMMIT_TYPES[type] ?? { label: type, color: "var(--text-muted)" };
    return `<span class="badge" style="background:${t.color}20;color:${t.color};border:1px solid ${t.color}40">${escHtml(t.label)}</span>`;
  }
  function commitScopeBadge(scope) {
    if (!scope) return "";
    return `<span class="badge" style="background:var(--bg-overlay);color:var(--color-purple);border:1px solid var(--color-purple-bg)">${escHtml(scope)}</span>`;
  }
  function parseCommitMeta(message) {
    const meta = {};
    const patterns = [
      /section:([\w-]+)/i,
      /track:([\w-]+)/i,
      /key:([\w#b]+\s*(?:major|minor|maj|min)?)/i,
      /tempo:(\d+)/i,
      /bpm:(\d+)/i
    ];
    const keys = ["section", "track", "key", "tempo", "bpm"];
    patterns.forEach((re, i) => {
      const m = message.match(re);
      if (m) meta[keys[i]] = m[1];
    });
    return meta;
  }
  var REACTION_BAR_EMOJIS = ["\u{1F525}", "\u2764\uFE0F", "\u{1F44F}", "\u2728", "\u{1F3B5}", "\u{1F3B8}", "\u{1F3B9}", "\u{1F941}"];
  async function loadReactions(targetType, targetId, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const repoId = window.__repoId;
    let reactions = [];
    try {
      reactions = await apiFetch(
        "/repos/" + repoId + "/reactions?target_type=" + encodeURIComponent(targetType) + "&target_id=" + encodeURIComponent(targetId)
      );
    } catch {
      reactions = [];
    }
    const countMap = {};
    const reactedMap = {};
    (Array.isArray(reactions) ? reactions : []).forEach((r) => {
      countMap[r.emoji] = r.count;
      reactedMap[r.emoji] = r.reacted_by_me;
    });
    const safeTT = targetType.replace(/'/g, "");
    const safeTI = String(targetId).replace(/'/g, "");
    const safeCID = containerId.replace(/'/g, "");
    container.innerHTML = '<div class="reaction-bar">' + REACTION_BAR_EMOJIS.map((emoji) => {
      const count = countMap[emoji] ?? 0;
      const active = reactedMap[emoji] ? " reaction-btn--active" : "";
      const countHtml = count > 0 ? '<span class="reaction-count">' + count + "</span>" : "";
      return '<button class="reaction-btn' + active + `" onclick="toggleReaction('` + safeTT + "','" + safeTI + "','" + emoji + "','" + safeCID + `')" title="` + emoji + '">' + emoji + countHtml + "</button>";
    }).join("") + "</div>";
  }
  async function toggleReaction(targetType, targetId, emoji, containerId) {
    if (!getToken()) {
      showTokenForm("Sign in to react");
      return;
    }
    const repoId = window.__repoId;
    try {
      await apiFetch("/repos/" + repoId + "/reactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_type: targetType, target_id: String(targetId), emoji })
      });
      await loadReactions(targetType, targetId, containerId);
    } catch {
    }
  }
  document.addEventListener("htmx:configRequest", (evt) => {
    const token = getToken();
    if (token) evt.detail.headers["Authorization"] = "Bearer " + token;
  });
  document.addEventListener("htmx:afterSwap", () => {
    const repoId = window.__repoId;
    if (repoId) void initRepoNav(repoId);
  });
  async function loadNotifBadge() {
    if (!getToken()) return;
    try {
      const data = await apiFetch("/notifications");
      const unread = Array.isArray(data) ? data.filter((n) => !n.is_read).length : 0;
      const badge = document.getElementById("nav-notif-badge");
      if (badge) {
        badge.textContent = unread > 99 ? "99+" : String(unread);
        badge.style.display = unread > 0 ? "flex" : "none";
      }
    } catch (_) {
    }
  }
  function initPageGlobals() {
    if (getToken()) {
      const btn = document.getElementById("signout-btn");
      if (btn) btn.style.display = "";
    }
    loadNotifBadge();
    if (typeof window.lucide === "object") {
      window.lucide.createIcons();
    }
    const pageDataEl = document.getElementById("page-data");
    if (pageDataEl) {
      try {
        const pageData = JSON.parse(pageDataEl.textContent ?? "{}");
        dispatchPageModule(pageData);
      } catch (_) {
      }
    }
  }
  function dispatchPageModule(data) {
    const page = data["page"];
    if (!page) return;
    const pages = window.MusePages;
    if (pages && typeof pages[page] === "function") {
      pages[page](data);
    }
  }
  document.addEventListener("DOMContentLoaded", initPageGlobals);
  document.addEventListener("htmx:afterSettle", initPageGlobals);
  window.getToken = getToken;
  window.setToken = setToken;
  window.clearToken = clearToken;
  window.saveToken = saveToken;
  window.showTokenForm = showTokenForm;
  window.apiFetch = apiFetch;
  window.authHeaders = authHeaders;
  window.fmtDate = fmtDate;
  window.fmtRelative = fmtRelative;
  window.shortSha = shortSha;
  window.fmtDuration = fmtDuration;
  window.fmtSeconds = fmtSeconds;
  window.escHtml = escHtml;
  window.initRepoNav = initRepoNav;
  window.toggleStar = toggleStar;
  window.queueAudio = queueAudio;
  window.togglePlay = togglePlay;
  window.seekAudio = seekAudio;
  window.closePlayer = closePlayer;
  window.downloadArtifact = downloadArtifact;
  window.onTimeUpdate = onTimeUpdate;
  window.onMetadata = onMetadata;
  window.onAudioEnded = onAudioEnded;
  window.parseCommitMessage = parseCommitMessage;
  window.commitTypeBadge = commitTypeBadge;
  window.commitScopeBadge = commitScopeBadge;
  window.parseCommitMeta = parseCommitMeta;
  window.loadReactions = loadReactions;
  window.toggleReaction = toggleReaction;

  // musehub/templates/musehub/static/js/audio-player.ts
  var SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
  function fmtTime(secs) {
    if (!isFinite(secs) || secs < 0) return "0:00";
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  var AudioPlayer = class _AudioPlayer {
    _ws = null;
    _opts;
    _autoPlay = false;
    constructor(opts) {
      this._opts = opts;
    }
    static init(opts) {
      const player = new _AudioPlayer(opts);
      player._setup();
      return player;
    }
    _setup() {
      const self = this;
      const opts = this._opts;
      this._ws = WaveSurfer.create({
        container: opts.waveformEl,
        waveColor: "#4a5568",
        progressColor: "#1f6feb",
        cursorColor: "#58a6ff",
        height: 80,
        barWidth: 2,
        barGap: 1
      });
      this._ws.on("ready", () => {
        const dur = self._ws.getDuration();
        if (opts.timeDurEl) opts.timeDurEl.textContent = fmtTime(dur);
        if (opts.playBtnEl) opts.playBtnEl.disabled = false;
        if (self._autoPlay) {
          self._autoPlay = false;
          self._ws.play();
        }
      });
      this._ws.on("play", () => {
        if (opts.playBtnEl) opts.playBtnEl.innerHTML = "&#9646;&#9646;";
      });
      this._ws.on("pause", () => {
        if (opts.playBtnEl) opts.playBtnEl.innerHTML = "&#9654;";
      });
      this._ws.on("finish", () => {
        if (opts.playBtnEl) opts.playBtnEl.innerHTML = "&#9654;";
      });
      this._ws.on("timeupdate", (t) => {
        if (opts.timeCurEl) opts.timeCurEl.textContent = fmtTime(t);
      });
      this._ws.on("region-update", (region) => {
        const r = region;
        if (opts.loopInfoEl) {
          opts.loopInfoEl.textContent = "Loop: " + fmtTime(r.start) + " \u2013 " + fmtTime(r.end);
          opts.loopInfoEl.style.display = "";
        }
        if (opts.loopBtnEl) opts.loopBtnEl.style.display = "";
      });
      this._ws.on("region-clear", () => {
        if (opts.loopInfoEl) opts.loopInfoEl.style.display = "none";
        if (opts.loopBtnEl) opts.loopBtnEl.style.display = "none";
      });
      this._ws.on("error", (msg) => {
        if (opts.waveformEl) {
          const errEl = document.createElement("p");
          errEl.style.cssText = "color:#f85149;padding:16px;margin:0;";
          errEl.textContent = "\u274C Audio unavailable: " + String(msg);
          opts.waveformEl.appendChild(errEl);
        }
      });
      if (opts.playBtnEl) {
        opts.playBtnEl.disabled = true;
        opts.playBtnEl.addEventListener("click", () => self._ws.playPause());
      }
      if (opts.speedSelEl) {
        SPEEDS.forEach((s, idx) => {
          const opt = document.createElement("option");
          opt.value = String(s);
          opt.textContent = s + "x";
          if (idx === 2) opt.selected = true;
          opts.speedSelEl.appendChild(opt);
        });
        opts.speedSelEl.addEventListener("change", function() {
          self._ws.setPlaybackRate(parseFloat(this.value));
        });
      }
      if (opts.loopBtnEl) {
        opts.loopBtnEl.style.display = "none";
        opts.loopBtnEl.addEventListener("click", () => self._ws.clearRegion());
      }
      if (opts.loopInfoEl) opts.loopInfoEl.style.display = "none";
      if (opts.volSliderEl) {
        opts.volSliderEl.addEventListener("input", function() {
          self._ws.setVolume(parseFloat(this.value));
        });
      }
      document.addEventListener("keydown", (e) => {
        const tag = e.target?.tagName ?? "";
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        if (e.code === "Space") {
          e.preventDefault();
          self._ws.playPause();
        } else if (e.code === "KeyL") {
          self._ws.clearRegion();
        } else if (e.code === "ArrowLeft") {
          const t = Math.max(0, self._ws.getCurrentTime() - 5);
          const d = self._ws.getDuration();
          if (d > 0) self._ws.seekTo(t / d);
        } else if (e.code === "ArrowRight") {
          const tc = self._ws.getCurrentTime() + 5;
          const dc = self._ws.getDuration();
          if (dc > 0) self._ws.seekTo(Math.min(1, tc / dc));
        }
      });
    }
    load(url, autoPlay = false) {
      this._autoPlay = autoPlay;
      if (this._opts.playBtnEl) this._opts.playBtnEl.disabled = true;
      if (this._opts.timeCurEl) this._opts.timeCurEl.textContent = "0:00";
      if (this._opts.timeDurEl) this._opts.timeDurEl.textContent = "0:00";
      this._ws.load(url);
    }
    destroy() {
      if (this._ws) {
        this._ws.destroy();
        this._ws = null;
      }
    }
  };
  window.AudioPlayer = AudioPlayer;

  // musehub/templates/musehub/static/js/piano-roll.ts
  var TRACK_COLORS = [
    "#58a6ff",
    // blue
    "#3fb950",
    // green
    "#f0883e",
    // orange
    "#bc8cff",
    // purple
    "#ff7b72",
    // red
    "#79c0ff",
    // light blue
    "#56d364",
    // light green
    "#ffa657",
    // light orange
    "#d2a8ff",
    // light purple
    "#ffa198"
    // light red
  ];
  var NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  function pitchToName(pitch) {
    const octave = Math.floor(pitch / 12) - 1;
    return NOTE_NAMES[pitch % 12] + octave;
  }
  function isBlackKey(pitch) {
    const pc = pitch % 12;
    return pc === 1 || pc === 3 || pc === 6 || pc === 8 || pc === 10;
  }
  var KEY_WIDTH = 36;
  var MIN_PITCH = 21;
  var MAX_PITCH = 108;
  function escHtml2(s) {
    if (s === null || s === void 0) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function render(midi, container, opts = {}) {
    const tracks = midi.tracks ?? [];
    const tempoBpm = midi.tempo_bpm ?? 120;
    const timeSig = midi.time_signature ?? "4/4";
    const totalBeats = midi.total_beats ?? 0;
    let selectedTrack = opts.selectedTrack ?? -1;
    let allNotes = [];
    tracks.forEach((t) => {
      if (selectedTrack === -1 || t.track_id === selectedTrack) {
        (t.notes ?? []).forEach((n) => allNotes.push(n));
      }
    });
    if (allNotes.length === 0) {
      container.innerHTML = '<p style="color:var(--text-muted);padding:16px;">No MIDI notes found.</p>';
      return;
    }
    let pitchMin = Math.max(
      MIN_PITCH,
      allNotes.reduce((m, n) => Math.min(m, n.pitch), 127) - 2
    );
    let pitchMax = Math.min(
      MAX_PITCH,
      allNotes.reduce((m, n) => Math.max(m, n.pitch), 0) + 2
    );
    let pitchRange = pitchMax - pitchMin + 1;
    container.innerHTML = pianoRollHtml(midi, tracks, selectedTrack, totalBeats, tempoBpm, timeSig);
    const outerEl = container.querySelector("#piano-roll-outer");
    const canvasEl = container.querySelector("#piano-canvas");
    const tooltip = document.querySelector(".piano-roll-tooltip");
    if (!outerEl || !canvasEl) return;
    const outer = outerEl;
    const canvas = canvasEl;
    let zoomX = 60;
    let zoomY = 14;
    let panX = 0;
    let panY = 0;
    let isPanning = false;
    let lastMouseX = 0;
    let lastMouseY = 0;
    const dpr = window.devicePixelRatio || 1;
    function outerW() {
      return outer.clientWidth || 800;
    }
    function outerH() {
      return Math.min(Math.max(pitchRange * zoomY + 40, 200), 600);
    }
    function resize() {
      const w = outerW();
      const h = outerH();
      outer.style.height = h + "px";
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
    }
    function pitchToY(pitch, h) {
      const row = pitchMax - pitch - panY;
      return 20 + row * zoomY;
    }
    function beatToX(beat, rollW) {
      return KEY_WIDTH + (beat - panX) * zoomX;
    }
    function draw() {
      const w = outerW();
      const h = outerH();
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const rollW = w - KEY_WIDTH;
      ctx.fillStyle = "#0d1117";
      ctx.fillRect(0, 0, w, h);
      for (let p = pitchMin; p <= pitchMax; p++) {
        const y = pitchToY(p, h);
        ctx.fillStyle = isBlackKey(p) ? "#131820" : "#0d1117";
        ctx.fillRect(KEY_WIDTH, y, rollW, zoomY);
        if (p % 12 === 0) {
          ctx.fillStyle = "#1f2937";
          ctx.fillRect(KEY_WIDTH, y, rollW, 1);
        }
      }
      const beatsPerScreen = rollW / zoomX;
      const beatStart = Math.floor(panX);
      const beatEnd = Math.ceil(panX + beatsPerScreen + 1);
      const beatStep = zoomX < 8 ? 8 : zoomX < 20 ? 4 : zoomX < 40 ? 2 : 1;
      for (let b = beatStart; b <= beatEnd; b += beatStep) {
        const bx = beatToX(b, rollW);
        const isMeasure = b % 4 === 0;
        ctx.strokeStyle = isMeasure ? "#30363d" : "#1a2030";
        ctx.lineWidth = isMeasure ? 1 : 0.5;
        ctx.beginPath();
        ctx.moveTo(bx, 20);
        ctx.lineTo(bx, h);
        ctx.stroke();
        if (isMeasure && bx >= KEY_WIDTH) {
          ctx.fillStyle = "#8b949e";
          ctx.font = "9px monospace";
          ctx.fillText(String(b), bx + 2, 14);
        }
      }
      allNotes.forEach((n) => {
        const x1 = beatToX(n.start_beat, rollW);
        const x2 = beatToX(n.start_beat + n.duration_beats, rollW);
        const ny = pitchToY(n.pitch, h);
        const nw = Math.max(x2 - x1 - 1, 2);
        const nh = Math.max(zoomY - 1, 3);
        if (x2 < KEY_WIDTH || x1 > w) return;
        const trackColor = TRACK_COLORS[n.track_id % TRACK_COLORS.length];
        const alpha = 0.4 + n.velocity / 127 * 0.6;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = trackColor;
        ctx.fillRect(Math.max(x1, KEY_WIDTH), ny + 1, nw, nh);
        ctx.globalAlpha = alpha * 0.8;
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(Math.max(x1, KEY_WIDTH), ny + 1, nw, 1);
        ctx.globalAlpha = 1;
      });
      for (let pk = pitchMin; pk <= pitchMax; pk++) {
        const pky = pitchToY(pk, h);
        const black = isBlackKey(pk);
        ctx.fillStyle = black ? "#1a1a1a" : "#e6edf3";
        ctx.fillRect(0, pky + 1, black ? KEY_WIDTH * 0.65 : KEY_WIDTH - 1, Math.max(zoomY - 1, 2));
        if (!black && pk % 12 === 0) {
          ctx.fillStyle = "#58a6ff";
          ctx.font = "9px monospace";
          ctx.fillText(pitchToName(pk), 2, pky + zoomY - 2);
        }
      }
      ctx.fillStyle = "#161b22";
      ctx.fillRect(KEY_WIDTH, 0, rollW, 20);
      ctx.fillStyle = "#0d1117";
      ctx.fillRect(0, 0, KEY_WIDTH, 20);
      ctx.fillStyle = "#8b949e";
      ctx.font = "10px monospace";
      ctx.fillText(tempoBpm.toFixed(1) + " BPM  " + timeSig, KEY_WIDTH + 6, 13);
    }
    const zoomXInput = container.querySelector("#zoom-x");
    const zoomYInput = container.querySelector("#zoom-y");
    const trackSel = container.querySelector("#track-sel");
    zoomXInput?.addEventListener("input", function() {
      zoomX = parseInt(this.value, 10);
      resize();
      draw();
    });
    zoomYInput?.addEventListener("input", function() {
      zoomY = parseInt(this.value, 10);
      resize();
      draw();
    });
    trackSel?.addEventListener("change", function() {
      selectedTrack = parseInt(this.value, 10);
      allNotes = [];
      tracks.forEach((t) => {
        if (selectedTrack === -1 || t.track_id === selectedTrack) {
          (t.notes ?? []).forEach((n) => allNotes.push(n));
        }
      });
      if (allNotes.length > 0) {
        pitchMin = Math.max(MIN_PITCH, allNotes.reduce((m, n) => Math.min(m, n.pitch), 127) - 2);
        pitchMax = Math.min(MAX_PITCH, allNotes.reduce((m, n) => Math.max(m, n.pitch), 0) + 2);
        pitchRange = pitchMax - pitchMin + 1;
      }
      resize();
      draw();
    });
    canvas.addEventListener("mousedown", (e) => {
      isPanning = true;
      lastMouseX = e.clientX;
      lastMouseY = e.clientY;
      outer.classList.add("panning");
    });
    window.addEventListener("mousemove", (e) => {
      if (isPanning) {
        const dx = e.clientX - lastMouseX;
        const dy = e.clientY - lastMouseY;
        panX = Math.max(0, panX - dx / zoomX);
        panY = Math.max(0, panY - dy / zoomY);
        lastMouseX = e.clientX;
        lastMouseY = e.clientY;
        draw();
      } else {
        showTooltip(e);
      }
    });
    window.addEventListener("mouseup", () => {
      isPanning = false;
      outer.classList.remove("panning");
    });
    canvas.addEventListener("mouseleave", () => {
      if (tooltip) tooltip.style.display = "none";
    });
    function showTooltip(e) {
      if (!tooltip) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      if (mx < KEY_WIDTH || my < 20) {
        tooltip.style.display = "none";
        return;
      }
      const beat = panX + (mx - KEY_WIDTH) / zoomX;
      const pitch = pitchMax - Math.floor((my - 20) / zoomY) - Math.round(panY);
      const hit = allNotes.find(
        (n) => n.pitch === pitch && n.start_beat <= beat && n.start_beat + n.duration_beats >= beat
      );
      if (!hit) {
        tooltip.style.display = "none";
        return;
      }
      tooltip.innerHTML = "<strong>" + pitchToName(hit.pitch) + "</strong> (MIDI " + hit.pitch + ")<br>Beat: " + hit.start_beat.toFixed(2) + "<br>Duration: " + hit.duration_beats.toFixed(2) + " beats<br>Velocity: " + hit.velocity + "<br>Track: " + hit.track_id + " / Ch " + hit.channel;
      tooltip.style.display = "block";
      tooltip.style.left = e.clientX + 14 + "px";
      tooltip.style.top = e.clientY - 10 + "px";
    }
    window.addEventListener("resize", () => {
      resize();
      draw();
    });
    resize();
    draw();
  }
  function pianoRollHtml(_midi, tracks, selectedTrack, totalBeats, tempoBpm, timeSig) {
    const trackOpts = '<option value="-1">All tracks</option>' + tracks.map((t) => {
      const sel = t.track_id === selectedTrack ? " selected" : "";
      return '<option value="' + t.track_id + '"' + sel + ">" + escHtml2(t.name ?? "Track " + t.track_id) + " (" + (t.notes ?? []).length + " notes)</option>";
    }).join("");
    const legendItems = tracks.map((t) => {
      const color = TRACK_COLORS[t.track_id % TRACK_COLORS.length];
      return '<div class="track-legend-item"><div class="track-legend-swatch" style="background:' + color + '"></div>' + escHtml2(t.name ?? "Track " + t.track_id) + "</div>";
    }).join("");
    return '<div class="piano-roll-wrapper"><div class="piano-roll-controls"><label>Track: <select id="track-sel">' + trackOpts + '</select></label><label>H-Zoom: <input type="range" id="zoom-x" min="4" max="200" value="60" style="width:80px"></label><label>V-Zoom: <input type="range" id="zoom-y" min="4" max="40" value="14" style="width:60px"></label><span style="font-size:12px;color:#8b949e;margin-left:auto">' + totalBeats.toFixed(1) + " beats &bull; " + tempoBpm.toFixed(1) + " BPM &bull; " + escHtml2(timeSig) + '</span></div><div id="piano-roll-outer"><canvas id="piano-canvas"></canvas></div><div class="track-legend">' + legendItems + "</div></div>";
  }
  var PianoRoll = { render };
  window.PianoRoll = PianoRoll;

  // musehub/templates/musehub/static/js/pages/repo-page.ts
  function initRepoPage(data) {
    const repoId = data.repo_id;
    if (repoId && typeof window.initRepoNav === "function") {
      window.initRepoNav(String(repoId));
    }
  }

  // musehub/templates/musehub/static/js/pages/issue-list.ts
  function bodyPreview(text, maxLen = 120) {
    if (!text) return "";
    const stripped = text.replace(/[#*`>\-_]/g, "").trim();
    return stripped.length > maxLen ? stripped.slice(0, maxLen) + "\u2026" : stripped;
  }
  var ISSUE_TEMPLATES = [
    { id: "blank", icon: "\u{1F4DD}", title: "Blank Issue", description: "Start with a clean slate.", body: "" },
    { id: "bug", icon: "\u{1F41B}", title: "Bug Report", description: "Something isn't working as expected.", body: "## What happened?\n\n\n## Steps to reproduce\n\n1. \n2. \n3. \n\n## Expected behaviour\n\n\n## Actual behaviour\n\n" },
    { id: "feature", icon: "\u2728", title: "Feature Request", description: "Suggest a new musical idea or capability.", body: "## Summary\n\n\n## Motivation\n\n\n## Proposed approach\n\n" },
    { id: "arrangement", icon: "\u{1F3B5}", title: "Arrangement Issue", description: "Track needs musical arrangement work.", body: "## Track / Section\n\n\n## Current arrangement\n\n\n## Desired arrangement\n\n\n## Musical context\n\n" },
    { id: "theory", icon: "\u{1F3BC}", title: "Music Theory", description: "Related to harmony, rhythm, or theory decisions.", body: "## Theory concern\n\n\n## Affected section / instrument\n\n\n## Suggested resolution\n\n" }
  ];
  var selectedIssues = /* @__PURE__ */ new Set();
  function showTemplatePicker() {
    const panel = document.getElementById("create-issue-panel");
    const picker = document.getElementById("template-picker");
    if (!panel || !picker) return;
    picker.style.display = "";
    panel.style.display = "none";
  }
  function selectTemplate(tplId) {
    const tpl = ISSUE_TEMPLATES.find((t) => t.id === tplId);
    if (!tpl) return;
    const bodyEl = document.getElementById("issue-body");
    if (bodyEl) bodyEl.value = tpl.body;
    const picker = document.getElementById("template-picker");
    if (picker) picker.style.display = "none";
    const panel = document.getElementById("create-issue-panel");
    if (panel) panel.style.display = "";
    const titleEl = document.getElementById("issue-title");
    if (titleEl) titleEl.focus();
  }
  function toggleIssueSelect(issueId, checked) {
    if (checked) {
      selectedIssues.add(issueId);
    } else {
      selectedIssues.delete(issueId);
    }
    updateBulkToolbar();
  }
  function updateBulkToolbar() {
    const toolbar = document.getElementById("bulk-toolbar");
    const countEl = document.getElementById("bulk-count");
    if (!toolbar || !countEl) return;
    const n = selectedIssues.size;
    if (n > 0) {
      toolbar.classList.add("visible");
      countEl.textContent = n === 1 ? "1 issue selected" : `${n} issues selected`;
    } else {
      toolbar.classList.remove("visible");
    }
  }
  function deselectAll() {
    selectedIssues.clear();
    document.querySelectorAll(".issue-row-check").forEach((c) => {
      c.checked = false;
    });
    updateBulkToolbar();
  }
  function bulkClose() {
    if (selectedIssues.size > 0 && confirm(`Close ${selectedIssues.size} issue(s)?`)) location.reload();
  }
  function bulkReopen() {
    if (selectedIssues.size > 0 && confirm(`Reopen ${selectedIssues.size} issue(s)?`)) location.reload();
  }
  function bulkAssignLabel() {
    const s = document.getElementById("bulk-label-select");
    if (!s?.value) {
      alert("Please select a label first.");
      return;
    }
    if (selectedIssues.size > 0) location.reload();
  }
  function bulkAssignMilestone() {
    const s = document.getElementById("bulk-milestone-select");
    if (!s?.value) {
      alert("Please select a milestone first.");
      return;
    }
    if (selectedIssues.size > 0) location.reload();
  }
  function initIssueList(data) {
    initRepoPage(data);
    window.showTemplatePicker = showTemplatePicker;
    window.selectTemplate = selectTemplate;
    window.toggleIssueSelect = toggleIssueSelect;
    window.deselectAll = deselectAll;
    window.bulkClose = bulkClose;
    window.bulkReopen = bulkReopen;
    window.bulkAssignLabel = bulkAssignLabel;
    window.bulkAssignMilestone = bulkAssignMilestone;
    window.bodyPreview = bodyPreview;
  }

  // musehub/templates/musehub/static/js/pages/new-repo.ts
  function initTagInput(containerId, hiddenInputId) {
    const container = document.getElementById(containerId);
    const hidden = document.getElementById(hiddenInputId);
    if (!container || !hidden) return;
    const textInput = container.querySelector(".tag-text-input");
    if (!textInput) return;
    let tags = hidden.value ? hidden.value.split(",").filter(Boolean) : [];
    function render2() {
      container.querySelectorAll(".tag-pill").forEach((p) => p.remove());
      tags.forEach((tag) => {
        const pill = document.createElement("span");
        pill.className = "tag-pill";
        pill.textContent = tag + " ";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tag-pill-remove";
        btn.textContent = "\xD7";
        btn.addEventListener("click", () => {
          tags = tags.filter((t) => t !== tag);
          render2();
        });
        pill.appendChild(btn);
        container.insertBefore(pill, textInput);
      });
      hidden.value = tags.join(",");
    }
    textInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        const val = textInput.value.trim().replace(/,/g, "");
        if (val && !tags.includes(val)) {
          tags.push(val);
          render2();
        }
        textInput.value = "";
      } else if (e.key === "Backspace" && textInput.value === "" && tags.length > 0) {
        tags.pop();
        render2();
      }
    });
    container.addEventListener("click", () => textInput.focus());
    render2();
  }
  function initVisibilityCards() {
    document.querySelectorAll(".visibility-card").forEach((card) => {
      const el = card;
      el.addEventListener("click", () => {
        document.querySelectorAll(".visibility-card").forEach((c) => {
          c.setAttribute("aria-checked", "false");
          c.classList.remove("selected");
        });
        el.setAttribute("aria-checked", "true");
        el.classList.add("selected");
        const radio = el.querySelector("input[type=radio]");
        if (radio) radio.checked = true;
      });
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") el.click();
      });
    });
  }
  function initNewRepo(_data) {
    initTagInput("tag-input-container", "tags-hidden");
    initVisibilityCards();
  }

  // musehub/templates/musehub/static/js/pages/piano-roll-page.ts
  function attachTransportControls() {
    const playBtn = document.getElementById("play-btn");
    const stopBtn = document.getElementById("stop-btn");
    if (playBtn) {
      playBtn.addEventListener("click", () => {
        const pr = window.PianoRoll;
        if (pr?.play) pr.play();
      });
    }
    if (stopBtn) {
      stopBtn.addEventListener("click", () => {
        const pr = window.PianoRoll;
        if (pr?.stop) pr.stop();
      });
    }
  }
  async function legacyLoad(repoId) {
    const canvas = document.getElementById("piano-canvas");
    if (!canvas) return;
    const pr = window.PianoRoll;
    if (pr?.init) return;
    const midiUrl = canvas.dataset.midiUrl;
    const rollPath = canvas.dataset.path ?? null;
    const apiFetch2 = window.apiFetch;
    if (!apiFetch2) return;
    try {
      const outer = document.getElementById("piano-roll-outer");
      if (rollPath) {
        const objData = await apiFetch2("/repos/" + encodeURIComponent(repoId) + "/objects?limit=500");
        const obj = (objData.objects ?? []).find((o) => o.path === rollPath);
        if (obj && typeof window.renderFromObjectId === "function") {
          window.renderFromObjectId(repoId, obj.objectId, outer);
        }
      } else if (midiUrl) {
        if (typeof window.renderFromUrl === "function") {
          window.renderFromUrl(midiUrl, outer);
        }
      }
    } catch (_) {
    }
  }
  async function initPianoRollPage(data) {
    initRepoPage(data);
    attachTransportControls();
    if (data.repo_id) await legacyLoad(String(data.repo_id));
  }

  // musehub/templates/musehub/static/js/pages/listen.ts
  var mixAudio = null;
  var trackAudios = {};
  function fmtTime2(s) {
    if (!isFinite(s) || s < 0) return "0:00";
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ":" + (sec < 10 ? "0" : "") + sec;
  }
  function fmtBytes(n) {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }
  function miniWaveform(objectId, _isPlaying) {
    const seed = objectId ? objectId.charCodeAt(objectId.length - 1) : 0;
    const heights = [];
    for (let i = 0; i < 16; i++) {
      heights.push(Math.round(20 + Math.abs(Math.sin((seed + i * 7) * 0.8)) * 45));
    }
    return heights.map((h) => `<div class="track-waveform-bar" style="height:${h}%"></div>`).join("");
  }
  function pauseAllTracks() {
    Object.values(trackAudios).forEach((a) => {
      if (!a.paused) a.pause();
    });
    document.querySelectorAll(".track-play-btn").forEach((b) => {
      b.innerHTML = "&#9654;";
      b.classList.remove("is-playing");
    });
    document.querySelectorAll(".track-row").forEach((r) => r.classList.remove("is-playing"));
  }
  function renderMixPlayer(url, _title) {
    return `
  <div class="listen-player-card">
    <div class="listen-player-title">Full Mix</div>
    <div class="listen-player-sub">Master render \u2014 all tracks combined</div>
    <div class="listen-controls">
      <button id="mix-play-btn" class="listen-play-btn" disabled title="Play / Pause">&#9654;</button>
      <div class="listen-progress-wrap">
        <div id="mix-progress-bar" class="listen-progress-bar">
          <div id="mix-progress-fill" class="listen-progress-fill"></div>
        </div>
        <div class="listen-time-row">
          <span id="mix-time-cur">0:00</span>
          <span id="mix-time-dur">\u2014</span>
        </div>
      </div>
    </div>
    <div class="listen-actions">
      <a href="${url}" download class="btn btn-secondary btn-sm">&#8595; Download</a>
    </div>
  </div>`;
  }
  function initMixPlayer(url) {
    mixAudio = new Audio();
    mixAudio.preload = "metadata";
    const playBtn = document.getElementById("mix-play-btn");
    const fill = document.getElementById("mix-progress-fill");
    const bar = document.getElementById("mix-progress-bar");
    const timeCur = document.getElementById("mix-time-cur");
    const timeDur = document.getElementById("mix-time-dur");
    if (!playBtn) return;
    mixAudio.addEventListener("canplay", () => {
      playBtn.disabled = false;
    });
    mixAudio.addEventListener("timeupdate", () => {
      const pct = mixAudio.duration ? mixAudio.currentTime / mixAudio.duration * 100 : 0;
      if (fill) fill.style.width = pct + "%";
      if (timeCur) timeCur.textContent = fmtTime2(mixAudio.currentTime);
    });
    mixAudio.addEventListener("durationchange", () => {
      if (timeDur) timeDur.textContent = fmtTime2(mixAudio.duration);
    });
    mixAudio.addEventListener("ended", () => {
      playBtn.innerHTML = "&#9654;";
      if (fill) fill.style.width = "0%";
      mixAudio.currentTime = 0;
    });
    mixAudio.addEventListener("error", () => {
      playBtn.disabled = true;
      playBtn.title = "Audio unavailable";
    });
    playBtn.addEventListener("click", () => {
      pauseAllTracks();
      if (mixAudio.paused) {
        mixAudio.src = url;
        mixAudio.play();
        playBtn.innerHTML = "&#9646;&#9646;";
      } else {
        mixAudio.pause();
        playBtn.innerHTML = "&#9654;";
      }
    });
    if (bar) {
      bar.addEventListener("click", (e) => {
        if (!mixAudio.duration) return;
        const rect = bar.getBoundingClientRect();
        mixAudio.currentTime = (e.clientX - rect.left) / rect.width * mixAudio.duration;
      });
    }
  }
  function renderTrackList(tracks) {
    return tracks.map((t) => {
      const safeId = CSS.escape(t.path);
      const dur = t.durationSec ? fmtTime2(t.durationSec) : "\u2014";
      const size = t.size ? fmtBytes(t.size) : "";
      const waveHtml = miniWaveform(t.objectId ?? t.path, false);
      return `
    <div class="track-row" id="track-row-${safeId}">
      <button class="track-play-btn" id="track-btn-${safeId}"
              onclick="window._listenPlayTrack(${JSON.stringify(t.path)}, ${JSON.stringify(t.url)}, 'track-btn-${safeId}', 'track-row-${safeId}')">&#9654;</button>
      <div class="track-info">
        <div class="track-name">${window.escHtml ? window.escHtml(t.name) : t.name}</div>
        <div class="track-path">${window.escHtml ? window.escHtml(t.path) : t.path}</div>
      </div>
      <div class="track-waveform">${waveHtml}</div>
      <div class="track-meta">${dur}${size ? " \xB7 " + size : ""}</div>
      <div class="track-row-actions">
        <a class="btn btn-secondary btn-sm" href="${t.url}" download title="Download">&#8595;</a>
      </div>
    </div>`;
    }).join("");
  }
  function playTrack(path, url, playBtnId, rowId) {
    if (mixAudio && !mixAudio.paused) {
      mixAudio.pause();
      const btn2 = document.getElementById("mix-play-btn");
      if (btn2) btn2.innerHTML = "&#9654;";
    }
    Object.keys(trackAudios).forEach((p) => {
      if (p !== path && !trackAudios[p].paused) {
        trackAudios[p].pause();
        const oldRow = document.getElementById("track-row-" + CSS.escape(p));
        if (oldRow) oldRow.classList.remove("is-playing");
        const oldBtn = document.getElementById("track-btn-" + CSS.escape(p));
        if (oldBtn) {
          oldBtn.innerHTML = "&#9654;";
          oldBtn.classList.remove("is-playing");
        }
      }
    });
    if (!trackAudios[path]) {
      trackAudios[path] = new Audio();
      trackAudios[path].preload = "metadata";
    }
    const audio = trackAudios[path];
    const btn = document.getElementById(playBtnId);
    const row = document.getElementById(rowId);
    if (audio.paused) {
      audio.src = url;
      audio.play();
      if (btn) {
        btn.innerHTML = "&#9646;&#9646;";
        btn.classList.add("is-playing");
      }
      if (row) row.classList.add("is-playing");
      audio.addEventListener("ended", () => {
        if (btn) {
          btn.innerHTML = "&#9654;";
          btn.classList.remove("is-playing");
        }
        if (row) row.classList.remove("is-playing");
      }, { once: true });
    } else {
      audio.pause();
      if (btn) {
        btn.innerHTML = "&#9654;";
        btn.classList.remove("is-playing");
      }
      if (row) row.classList.remove("is-playing");
    }
  }
  async function initListen(data) {
    initRepoPage(data);
    const repoId = String(data.repo_id ?? "");
    const ref = data.ref ?? "main";
    const apiBase = data.api_base ?? `/api/v1/musehub/repos/${encodeURIComponent(repoId)}`;
    window["_listenPlayTrack"] = playTrack;
    const content = document.getElementById("content");
    if (!content) return;
    content.innerHTML = '<p class="loading">Loading audio tracks\u2026</p>';
    try {
      const apiFetch2 = window.apiFetch;
      if (!apiFetch2) return;
      let listing;
      try {
        listing = await apiFetch2(apiBase.replace("/api/v1/musehub", "") + "/listen/" + encodeURIComponent(ref) + "/tracks");
      } catch (_) {
        listing = { hasRenders: false, tracks: [], fullMixUrl: null, ref, repoId };
      }
      if (!listing.hasRenders || listing.tracks.length === 0) {
        content.innerHTML = `
      <div class="no-renders-card">
        <span class="no-renders-icon">\u{1F3B5}</span>
        <div class="no-renders-title">No audio renders yet</div>
        <div class="no-renders-sub">Push a commit with .wav, .mp3, .flac, or .ogg files to see them here.</div>
      </div>`;
        return;
      }
      let html = "";
      if (listing.fullMixUrl) {
        html += renderMixPlayer(listing.fullMixUrl, "Full Mix");
      }
      html += `<div class="card"><div class="track-list">${renderTrackList(listing.tracks)}</div></div>`;
      content.innerHTML = html;
      if (listing.fullMixUrl) initMixPlayer(listing.fullMixUrl);
    } catch (e) {
      content.innerHTML = `<p class="error">Failed to load: ${e instanceof Error ? e.message : String(e)}</p>`;
    }
  }

  // musehub/templates/musehub/static/js/pages/commit-detail.ts
  function initCommitDetail(data) {
    initRepoPage(data);
    if (data.repo_id && data.commit_sha && typeof window.loadReactions === "function") {
      window.loadReactions("commit", String(data.commit_sha), "commit-reactions");
    }
  }

  // musehub/templates/musehub/static/js/pages/commit.ts
  function initCommit(data) {
    initRepoPage(data);
    if (data.repo_id && data.commit_id && typeof window.loadReactions === "function") {
      window.loadReactions("commit", String(data.commit_id), "commit-reactions");
    }
  }

  // musehub/templates/musehub/static/js/pages/user-profile.ts
  function esc(s) {
    if (!s) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function fmtRelative2(ts) {
    if (!ts) return "";
    const d = new Date(ts);
    const diff = Math.floor((Date.now() - d.getTime()) / 1e3);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }
  function renderHeatmap(stats) {
    const days = stats.days ?? [];
    const cols = [];
    let col = [];
    for (const day of days) {
      col.push(day);
      if (col.length === 7) {
        cols.push(col);
        col = [];
      }
    }
    if (col.length) cols.push(col);
    const colsHtml = cols.map((c) => {
      const cells = c.map(
        (d) => `<div class="heatmap-cell" data-intensity="${d.intensity}" title="${esc(d.date)}: ${d.count} commit${d.count !== 1 ? "s" : ""}"></div>`
      ).join("");
      return `<div class="heatmap-col">${cells}</div>`;
    }).join("");
    const legend = [0, 1, 2, 3].map((n) => `<div class="heatmap-cell" data-intensity="${n}" style="display:inline-block"></div>`).join("");
    const el = document.getElementById("heatmap-section");
    if (el) el.innerHTML = `
    <div class="card">
      <h2 style="margin-bottom:12px">\u{1F4C8} Contribution Activity</h2>
      <div class="heatmap-grid">${colsHtml}</div>
      <div style="display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12px;color:var(--text-muted)">
        Less ${legend} More &nbsp;\xB7&nbsp; ${stats.totalContributions ?? 0} contributions in the last year
        &nbsp;\xB7&nbsp; Longest streak: ${stats.longestStreak ?? 0} days
        &nbsp;\xB7&nbsp; Current streak: ${stats.currentStreak ?? 0} days
      </div>
    </div>`;
  }
  function renderBadges(badges) {
    const cards = badges.map((b) => {
      const cls = b.earned ? "earned" : "unearned";
      return `<div class="badge-card ${cls}" title="${esc(b.description)}">
      <div class="badge-icon">${esc(b.icon)}</div>
      <div class="badge-info">
        <div class="badge-name">${esc(b.name)}</div>
        <div class="badge-desc">${esc(b.description)}</div>
      </div>
    </div>`;
    }).join("");
    const earned = badges.filter((b) => b.earned).length;
    const el = document.getElementById("badges-section");
    if (el) el.innerHTML = `<div class="card"><h2 style="margin-bottom:12px">\u{1F3C6} Achievements (${earned}/${badges.length})</h2><div class="badge-grid">${cards}</div></div>`;
  }
  function renderPinned(pinnedRepos, _isOwner) {
    if (!pinnedRepos?.length) return;
    const cards = pinnedRepos.map((r) => {
      const genre = r.primaryGenre ? `<span>\u{1F3B5} ${esc(r.primaryGenre)}</span>` : "";
      const lang = r.language ? `<span>\u{1F524} ${esc(r.language)}</span>` : "";
      return `<div class="pinned-card">
      <h3><a href="/${esc(r.owner)}/${esc(r.slug)}">${esc(r.name)}</a></h3>
      ${r.description ? `<p class="pinned-desc">${esc(r.description)}</p>` : ""}
      <div class="pinned-meta">${genre}${lang}<span>\u2B50 ${r.starsCount ?? 0}</span><span>\u{1F374} ${r.forksCount ?? 0}</span></div>
    </div>`;
    }).join("");
    const el = document.getElementById("pinned-section");
    if (el) el.innerHTML = `<div class="card"><h2 style="margin-bottom:12px">\u{1F4CC} Pinned</h2><div class="pinned-grid">${cards}</div></div>`;
  }
  var currentUsername = "";
  var currentTab = "repos";
  var cachedRepos = [];
  function renderProfileHeader(profile) {
    const initial = (profile.displayName ?? profile.username ?? "?")[0].toUpperCase();
    const avatarHtml = profile.avatarUrl ? `<div class="avatar-lg"><img src="${esc(profile.avatarUrl)}" alt="${esc(profile.username)}" /></div>` : `<div class="avatar-lg" style="background:${esc(profile.avatarColor ?? "#1f6feb")}">${esc(initial)}</div>`;
    const isOwner = window.getToken ? !!window.getToken() : false;
    const el = document.getElementById("profile-hdr");
    if (el) el.innerHTML = `
    <div class="profile-hdr">
      ${avatarHtml}
      <div>
        <h1 style="margin:0 0 4px">${esc(profile.displayName ?? profile.username)}</h1>
        <div style="font-size:14px;color:var(--text-muted);margin-bottom:8px">@${esc(profile.username)}</div>
        ${profile.bio ? `<p style="font-size:14px;margin-bottom:8px">${esc(profile.bio)}</p>` : ""}
        <div style="display:flex;gap:16px;font-size:13px;color:var(--text-muted);flex-wrap:wrap">
          ${profile.location ? `<span>\u{1F4CD} ${esc(profile.location)}</span>` : ""}
          ${profile.website ? `<a href="${esc(profile.website)}" target="_blank" rel="noopener noreferrer">\u{1F517} ${esc(profile.website)}</a>` : ""}
          <span>\u{1F465} <strong>${profile.followersCount ?? 0}</strong> followers \xB7 <strong>${profile.followingCount ?? 0}</strong> following</span>
          <span>\u2B50 ${profile.starsCount ?? 0} stars</span>
        </div>
      </div>
    </div>`;
    return isOwner;
  }
  function renderReposTab(repos) {
    const tabContent = document.getElementById("tab-content");
    if (!tabContent) return;
    if (!repos.length) {
      tabContent.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No repositories yet.</p>';
      return;
    }
    tabContent.innerHTML = repos.map((r) => `
    <div class="repo-card" style="margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <a href="/${esc(r.owner)}/${esc(r.slug)}" style="font-weight:600;font-size:14px">${esc(r.name)}</a>
        ${r.isPrivate ? '<span class="badge badge-secondary">Private</span>' : ""}
      </div>
      ${r.description ? `<p style="font-size:13px;color:var(--text-muted);margin:4px 0 0">${esc(r.description)}</p>` : ""}
      <div style="display:flex;gap:12px;font-size:12px;color:var(--text-muted);margin-top:8px;flex-wrap:wrap">
        ${r.primaryGenre ? `<span>\u{1F3B5} ${esc(r.primaryGenre)}</span>` : ""}
        ${r.language ? `<span>\u{1F524} ${esc(r.language)}</span>` : ""}
        <span>\u2B50 ${r.starsCount ?? 0}</span>
        <span>\u{1F374} ${r.forksCount ?? 0}</span>
        ${r.updatedAt ? `<span>Updated ${fmtRelative2(r.updatedAt)}</span>` : ""}
      </div>
    </div>`).join("");
  }
  async function loadStarsTab() {
    const tabContent = document.getElementById("tab-content");
    if (!tabContent) return;
    tabContent.innerHTML = '<p class="loading">Loading starred repos\u2026</p>';
    try {
      const data = await fetch("/api/v1/users/" + currentUsername + "/starred").then((r) => r.json());
      if (!data.length) {
        tabContent.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No starred repos yet.</p>';
        return;
      }
      renderReposTab(data);
    } catch (_) {
      tabContent.innerHTML = '<p class="error">Failed to load starred repos.</p>';
    }
  }
  async function loadSocialTab(type) {
    const tabContent = document.getElementById("tab-content");
    if (!tabContent) return;
    tabContent.innerHTML = `<p class="loading">Loading ${type}\u2026</p>`;
    try {
      const url = type === "followers" ? "/api/v1/users/" + currentUsername + "/followers-list" : "/api/v1/users/" + currentUsername + "/following-list";
      const data = await fetch(url).then((r) => r.json());
      if (!data.length) {
        tabContent.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:24px">No ${type} yet.</p>`;
        return;
      }
      tabContent.innerHTML = data.map((u) => {
        const init = (u.displayName ?? u.username ?? "?")[0].toUpperCase();
        return `<div style="display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--border-default)">
        <div style="width:36px;height:36px;border-radius:50%;background:${esc(u.avatarColor ?? "#1f6feb")};display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;flex-shrink:0">${esc(init)}</div>
        <div><a href="/${esc(u.username)}" style="font-weight:600">${esc(u.displayName ?? u.username)}</a>
          ${u.bio ? `<p style="font-size:12px;color:var(--text-muted);margin:2px 0 0">${esc(u.bio)}</p>` : ""}</div>
      </div>`;
      }).join("");
    } catch (_) {
      tabContent.innerHTML = `<p class="error">Failed to load ${type}.</p>`;
    }
  }
  async function loadActivityTab(filter, page) {
    const tabContent = document.getElementById("tab-content");
    if (!tabContent) return;
    tabContent.innerHTML = '<p class="loading">Loading activity\u2026</p>';
    try {
      const data = await fetch(`/api/v1/users/${currentUsername}/activity?filter=${filter}&page=${page}&limit=20`).then((r) => r.json());
      const events = data.events ?? [];
      if (!events.length) {
        tabContent.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px">No activity yet.</p>';
        return;
      }
      const rows = events.map((e) => `
      <div class="activity-row">
        <span class="activity-icon">\u{1F4DD}</span>
        <div class="activity-body">
          <div class="activity-description">${esc(e.description ?? e.type)}</div>
          <div class="activity-meta">${fmtRelative2(e.timestamp)}${e.repo ? ` \xB7 <a href="/${esc(e.repo)}">${esc(e.repo)}</a>` : ""}</div>
        </div>
      </div>`).join("");
      const totalPages = Math.ceil((data.total ?? 0) / 20);
      const pageBtns = totalPages > 1 ? `
      <div style="display:flex;align-items:center;gap:8px;justify-content:center;margin-top:16px">
        ${page > 1 ? `<button class="btn btn-secondary" onclick="window._switchProfileTab('activity', '${filter}', ${page - 1})">&larr; Prev</button>` : ""}
        <span style="font-size:13px;color:var(--text-muted)">Page ${page} of ${totalPages}</span>
        ${page < totalPages ? `<button class="btn btn-secondary" onclick="window._switchProfileTab('activity', '${filter}', ${page + 1})">Next &rarr;</button>` : ""}
      </div>` : "";
      tabContent.innerHTML = rows + pageBtns;
    } catch (_) {
      tabContent.innerHTML = '<p class="error">Failed to load activity.</p>';
    }
  }
  function switchTab(tab, filter = "all", page = 1) {
    currentTab = tab;
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === tab);
    });
    switch (tab) {
      case "repos":
        renderReposTab(cachedRepos);
        break;
      case "stars":
        void loadStarsTab();
        break;
      case "followers":
        void loadSocialTab("followers");
        break;
      case "following":
        void loadSocialTab("following");
        break;
      case "activity":
        void loadActivityTab(filter, page);
        break;
    }
  }
  async function initUserProfile(data) {
    const username = data.username ?? "";
    if (!username) return;
    currentUsername = username;
    window.switchTab = switchTab;
    window["_switchProfileTab"] = switchTab;
    const profileHdr = document.getElementById("profile-hdr");
    const tabsSection = document.getElementById("tabs-section");
    if (profileHdr) profileHdr.innerHTML = '<p class="loading">Loading profile\u2026</p>';
    try {
      const [profileData, enhancedData] = await Promise.all([
        fetch("/api/v1/users/" + username).then((r) => {
          if (!r.ok) throw new Error(String(r.status));
          return r.json();
        }),
        fetch("/" + username + "?format=json").then((r) => {
          if (!r.ok) throw new Error(String(r.status));
          return r.json();
        })
      ]);
      const isOwner = renderProfileHeader(profileData);
      renderHeatmap(enhancedData.heatmap ?? {
        days: (profileData.contributionGraph ?? []).map((d) => ({ ...d, intensity: d.count === 0 ? 0 : d.count <= 3 ? 1 : d.count <= 6 ? 2 : 3 })),
        totalContributions: 0,
        longestStreak: 0,
        currentStreak: 0
      });
      renderBadges(enhancedData.badges ?? []);
      renderPinned(enhancedData.pinnedRepos ?? [], isOwner);
      cachedRepos = profileData.repos ?? [];
      if (tabsSection) tabsSection.style.display = "";
      renderReposTab(cachedRepos);
    } catch (e) {
      if (profileHdr) profileHdr.innerHTML = `<p class="error">\u2715 Could not load profile for @${esc(username)}: ${esc(e instanceof Error ? e.message : String(e))}</p>`;
    }
  }

  // musehub/templates/musehub/static/js/app.ts
  var MusePages = {
    "repo": (d) => initRepoPage(d),
    "issue-list": (d) => initIssueList(d),
    "new-repo": (d) => initNewRepo(d),
    "piano-roll": (d) => void initPianoRollPage(d),
    "listen": (d) => void initListen(d),
    "commit-detail": (d) => initCommitDetail(d),
    "commit": (d) => initCommit(d),
    "user-profile": (d) => void initUserProfile(d)
  };
  window.MusePages = MusePages;
})();
