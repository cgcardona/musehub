/**
 * piano-roll-player.js — Piano roll canvas rendering + Tone.js MIDI playback.
 *
 * Replaces the inline <script id="piano-roll-init"> module previously in
 * piano_roll.html. Runs as a standard script after piano-roll.js, midi-player.js,
 * and tone.min.js are loaded. No inline scripts — no 'unsafe-inline' CSP required.
 *
 * Flow:
 *   1. piano-roll.js renders the canvas from the /parse-midi endpoint.
 *   2. tone.min.js is already loaded synchronously above this script.
 *   3. createPlayerFromCanvas() builds a MidiPlayer using window.MidiPlayer.
 *   4. Transport buttons (play / pause / stop) drive the player.
 *   5. Player fires onProgress(beat) → drawPlayhead() overlays the canvas.
 */
(async function () {
  'use strict';

  var canvas      = document.getElementById('piano-canvas');
  var phCanvas    = document.getElementById('playhead-canvas');
  var playBtn     = document.getElementById('play-btn');
  var pauseBtn    = document.getElementById('pause-btn');
  var stopBtn     = document.getElementById('stop-btn');
  var tempoSldr   = document.getElementById('tempo-slider');
  var tempoDisp   = document.getElementById('tempo-display');
  var volSldr     = document.getElementById('volume-slider');
  var seekBar     = document.getElementById('seek-bar');
  var seekFill    = document.getElementById('seek-fill');
  var curTime     = document.getElementById('current-time');
  var toneStatus  = document.getElementById('tone-status');
  var toneStatusTxt = document.getElementById('tone-status-text');

  if (!canvas) { return; }

  // ── Piano roll canvas rendering ─────────────────────────────────────────────
  var midiUrl  = canvas.dataset.midiUrl;
  var midiData = null;

  if (midiUrl && window.PianoRoll) {
    try {
      var resp = await fetch(midiUrl, { credentials: 'include' });
      if (resp.ok) {
        midiData = await resp.json();
        var outer = document.getElementById('piano-roll-outer');
        if (outer && window.PianoRoll && window.PianoRoll.render) {
          window.PianoRoll.render(midiData, outer);
        }
      }
    } catch (e) {
      console.warn('Piano roll: could not fetch MIDI data', e);
    }
  }

  // ── Playhead canvas setup ───────────────────────────────────────────────────
  var phCtx = null;
  if (phCanvas) {
    phCtx = phCanvas.getContext('2d');
    function resizePlayhead() {
      var pr  = document.getElementById('piano-roll-outer');
      if (!pr) { return; }
      var dpr = window.devicePixelRatio || 1;
      phCanvas.width  = pr.clientWidth  * dpr;
      phCanvas.height = pr.clientHeight * dpr;
      phCanvas.style.width  = pr.clientWidth  + 'px';
      phCanvas.style.height = pr.clientHeight + 'px';
    }
    resizePlayhead();
    window.addEventListener('resize', resizePlayhead);
  }

  // ── State ───────────────────────────────────────────────────────────────────
  var player      = null;
  var totalBeats  = midiData ? (midiData.total_beats || 0) : 0;
  var currentBpm  = parseInt(canvas.dataset.tempo || '120', 10);
  var zoomX       = 60;
  var panX        = 0;
  var KEY_WIDTH   = 36;

  var zoomXSlider = document.getElementById('zoom-x');
  if (zoomXSlider) {
    zoomXSlider.addEventListener('input', function () {
      zoomX = parseInt(this.value, 10);
    });
  }

  // ── Build player ─────────────────────────────────────────────────────────────
  async function buildPlayer() {
    if (!midiData || !window.MidiPlayer) { return; }
    if (player) { player.dispose(); player = null; }

    player = new window.MidiPlayer(midiData, {
      bpmOverride: currentBpm,
      onProgress: function (beat) {
        if (totalBeats > 0 && seekFill) {
          seekFill.style.width = Math.min(100, (beat / totalBeats) * 100) + '%';
        }
        var secs = (beat * 60) / currentBpm;
        var mm   = Math.floor(secs / 60);
        var ss   = Math.floor(secs % 60);
        if (curTime) { curTime.textContent = mm + ':' + String(ss).padStart(2, '0'); }

        if (phCtx && phCanvas) {
          var pr  = document.getElementById('piano-roll-outer');
          var dpr = window.devicePixelRatio || 1;
          phCtx.clearRect(0, 0, phCanvas.width, phCanvas.height);
          phCtx.save();
          phCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
          var x = KEY_WIDTH + (beat - panX) * zoomX;
          if (x >= KEY_WIDTH && pr && x <= pr.clientWidth) {
            phCtx.globalAlpha  = 0.9;
            phCtx.strokeStyle  = '#f85149';
            phCtx.lineWidth    = 2;
            phCtx.setLineDash([4, 3]);
            phCtx.beginPath();
            phCtx.moveTo(x, 0);
            phCtx.lineTo(x, phCanvas.height / dpr);
            phCtx.stroke();
          }
          phCtx.restore();
        }
      },
      onEnd: function () {
        setUIStopped();
        if (phCtx && phCanvas) { phCtx.clearRect(0, 0, phCanvas.width, phCanvas.height); }
      },
    });
  }

  function setUIPlaying() {
    if (playBtn)  { playBtn.style.display  = 'none'; }
    if (pauseBtn) { pauseBtn.style.display = ''; }
  }
  function setUIPaused() {
    if (playBtn)  { playBtn.style.display  = ''; }
    if (pauseBtn) { pauseBtn.style.display = 'none'; }
  }
  function setUIStopped() {
    if (playBtn)  { playBtn.style.display  = ''; }
    if (pauseBtn) { pauseBtn.style.display = 'none'; }
    if (seekFill) { seekFill.style.width   = '0%'; }
    if (curTime)  { curTime.textContent    = '0:00'; }
  }

  // tone.min.js loads synchronously above this script; window.Tone is available.
  var toneReady = typeof window.Tone !== 'undefined';
  if (toneReady) {
    await buildPlayer();
  } else {
    // Fallback: wait for Tone.js if it arrives late (unexpected but safe).
    document.addEventListener('tone-ready', async function () {
      toneReady = true;
      await buildPlayer();
    });
  }

  // ── Transport buttons ───────────────────────────────────────────────────────
  if (playBtn) {
    playBtn.addEventListener('click', async function () {
      if (!toneReady) {
        if (toneStatus && toneStatusTxt) {
          toneStatus.style.display = 'flex';
          toneStatusTxt.textContent = 'Loading audio engine…';
        }
        return;
      }
      if (!player) { await buildPlayer(); }
      if (!player) { return; }
      await player.play();
      setUIPlaying();
    });
  }

  if (pauseBtn) {
    pauseBtn.addEventListener('click', function () {
      if (!player) { return; }
      player.pause();
      setUIPaused();
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener('click', function () {
      if (!player) { return; }
      player.stop();
      setUIStopped();
    });
  }

  // ── Tempo slider ─────────────────────────────────────────────────────────────
  if (tempoSldr) {
    tempoSldr.addEventListener('input', function () {
      currentBpm = parseInt(this.value, 10);
      if (tempoDisp) { tempoDisp.textContent = currentBpm + ' BPM'; }
      if (player) {
        var wasPlaying = player.isPlaying;
        player.stop();
        buildPlayer().then(function () { if (wasPlaying && player) { player.play(); } });
      }
    });
  }

  // ── Volume slider ─────────────────────────────────────────────────────────────
  if (volSldr && typeof window.Tone !== 'undefined') {
    volSldr.addEventListener('input', function () {
      try { window.Tone.getDestination().volume.value = parseInt(this.value, 10); } catch (_) {}
    });
  }

  // ── Seek bar ─────────────────────────────────────────────────────────────────
  if (seekBar) {
    seekBar.addEventListener('click', function (e) {
      if (!player || totalBeats <= 0) { return; }
      var rect = this.getBoundingClientRect();
      var pct  = (e.clientX - rect.left) / rect.width;
      player.seek(pct * totalBeats);
    });
  }

  // ── Keyboard: Space = play/pause ─────────────────────────────────────────────
  document.addEventListener('keydown', async function (e) {
    if (e.code === 'Space' && e.target === document.body) {
      e.preventDefault();
      if (!player) { return; }
      if (player.isPlaying) { player.pause(); setUIPaused(); }
      else { await player.play(); setUIPlaying(); }
    }
  });
})();
