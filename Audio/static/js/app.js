/* =========================================================================
   Silent Channel — frontend
   Organized as: small shared utilities -> per-page init functions -> a
   single DOMContentLoaded dispatcher keyed off body[data-page].
   ========================================================================= */

// ---------------------------------------------------------------- toast --
function toast(msg) {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 2800);
}

// ------------------------------------------------------------ canvas dpi --
function prepCanvas(canvas, cssHeight) {
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth || (canvas.parentElement && canvas.parentElement.clientWidth) || 300;
  canvas.width = Math.max(1, Math.round(cssWidth * dpr));
  canvas.height = Math.max(1, Math.round(cssHeight * dpr));
  canvas.style.height = cssHeight + "px";
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: cssWidth, h: cssHeight };
}

// ---------------------------------------------------------- viz: waveform --
function drawWaveformCompare(canvas, before, after) {
  const { ctx, w, h } = prepCanvas(canvas, 92);
  ctx.clearRect(0, 0, w, h);
  const mid = h / 2;
  const n = before.length;
  const bw = w / n;

  ctx.fillStyle = "rgba(143,155,161,0.32)";
  for (let i = 0; i < n; i++) {
    const amp = before[i] * mid * 0.88;
    ctx.fillRect(i * bw, mid - amp, Math.max(1, bw * 0.72), amp * 2);
  }

  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const amp = after[i] * mid * 0.88;
    const x = i * bw + bw / 2;
    if (i === 0) ctx.moveTo(x, mid - amp);
    else ctx.lineTo(x, mid - amp);
  }
  for (let i = n - 1; i >= 0; i--) {
    const amp = after[i] * mid * 0.88;
    const x = i * bw + bw / 2;
    ctx.lineTo(x, mid + amp);
  }
  ctx.closePath();
  ctx.fillStyle = "rgba(87,232,209,0.14)";
  ctx.fill();
  ctx.strokeStyle = "#57e8d1";
  ctx.lineWidth = 1.3;
  ctx.stroke();
}

function drawWaveformSingle(canvas, peaks, color) {
  const { ctx, w, h } = prepCanvas(canvas, 92);
  ctx.clearRect(0, 0, w, h);
  const mid = h / 2;
  const n = peaks.length;
  const bw = w / n;
  ctx.fillStyle = color || "#57e8d1";
  for (let i = 0; i < n; i++) {
    const amp = peaks[i] * mid * 0.88;
    ctx.fillRect(i * bw, mid - amp, Math.max(1, bw * 0.72), amp * 2);
  }
}

// ---------------------------------------------------------- viz: spectrum --
function drawSpectrum(canvas, freqs, db, bandRange, syncFreq) {
  const { ctx, w, h } = prepCanvas(canvas, 168);
  ctx.clearRect(0, 0, w, h);
  const maxFreq = freqs[freqs.length - 1] || 22050;
  const minDb = -90, maxDb = 0;
  const X = (f) => (f / maxFreq) * w;
  const Y = (d) => h - ((Math.max(d, minDb) - minDb) / (maxDb - minDb)) * h;

  ctx.fillStyle = "rgba(87,232,209,0.08)";
  ctx.fillRect(X(bandRange[0]), 0, X(bandRange[1]) - X(bandRange[0]), h);

  ctx.strokeStyle = "rgba(237,242,244,0.06)";
  ctx.lineWidth = 1;
  for (let k = 0; k <= 4; k++) {
    const y = (h * k) / 4;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(255,180,84,0.55)";
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(X(syncFreq), 0);
  ctx.lineTo(X(syncFreq), h);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.strokeStyle = "#57e8d1";
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  for (let i = 0; i < freqs.length; i++) {
    const x = X(freqs[i]);
    const y = Y(db[i]);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.fillStyle = "rgba(143,155,161,0.9)";
  ctx.font = '10px "IBM Plex Mono", monospace';
  ctx.fillText("0Hz", 3, h - 4);
  ctx.fillText((maxFreq / 1000).toFixed(0) + "kHz", w - 38, h - 4);
  ctx.fillStyle = "rgba(87,232,209,0.9)";
  ctx.fillText("watermark band", X(bandRange[0]) + 4, 12);
}

// -------------------------------------------------------------- viz: gauge --
function gaugeSVG(percent, color) {
  const r = 34, c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, percent));
  const offset = c * (1 - pct / 100);
  return `<svg width="84" height="84" viewBox="0 0 84 84">
    <circle cx="42" cy="42" r="${r}" stroke="rgba(237,242,244,0.09)" stroke-width="7" fill="none"/>
    <circle cx="42" cy="42" r="${r}" stroke="${color}" stroke-width="7" fill="none" stroke-linecap="round"
      stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${offset.toFixed(2)}"
      transform="rotate(-90 42 42)" style="transition: stroke-dashoffset .8s ease;"/>
  </svg>`;
}

// ---------------------------------------------------------------- typing --
function typeWriter(el, text, speed) {
  el.textContent = "";
  speed = speed || 16;
  let i = 0;
  return new Promise((resolve) => {
    if (!text) { resolve(); return; }
    const timer = setInterval(() => {
      el.textContent += text[i];
      i++;
      if (i >= text.length) {
        clearInterval(timer);
        resolve();
      }
    }, speed);
  });
}

// ------------------------------------------------------------- dropzones --
const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

function uploadSizeMessage(file) {
  const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
  return `${file.name} is ${sizeMb} MB. Please use an audio file smaller than 4 MB.`;
}

function attachDropzone(dropzone, input, filenameEl, onFile) {
  if (!dropzone || !input) return;
  const open = () => input.click();
  dropzone.addEventListener("click", open);
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
  });
  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) {
      if (file.size > MAX_UPLOAD_BYTES) { toast(uploadSizeMessage(file)); return; }
      input.files = e.dataTransfer.files;
      if (filenameEl) filenameEl.textContent = file.name;
      if (onFile) onFile(file);
    }
  });
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (file) {
      if (file.size > MAX_UPLOAD_BYTES) {
        input.value = "";
        if (filenameEl) filenameEl.textContent = "";
        toast(uploadSizeMessage(file));
        return;
      }
      if (filenameEl) filenameEl.textContent = file.name;
      if (onFile) onFile(file);
    }
  });
}

// ------------------------------------------------------- progress chains --
function runProgress(containerEl, stepOrder, promise) {
  if (!containerEl) return promise;
  containerEl.style.display = "flex";
  const nodes = stepOrder.map((s) => containerEl.querySelector(`[data-step="${s}"]`));
  let i = 0;
  nodes.forEach((n) => n && n.classList.remove("active", "done"));

  const tick = () => {
    if (i > 0 && nodes[i - 1]) nodes[i - 1].classList.replace("active", "done");
    if (i < nodes.length - 1 && nodes[i]) nodes[i].classList.add("active");
    i++;
  };
  tick();
  const interval = setInterval(() => {
    if (i < nodes.length - 1) tick();
  }, 420);

  return promise.finally(() => {
    clearInterval(interval);
    nodes.forEach((n) => n && n.classList.add("done"));
    nodes.forEach((n) => n && n.classList.remove("active"));
  });
}

// ============================================================================
// HOME — hero waterfall
// ============================================================================
function initHero() {
  const canvas = document.getElementById("heroCanvas");
  if (!canvas) return;

  const bufW = 96, bufH = 72;
  const buffer = new Float32Array(bufW * bufH); // row-major, row 0 = newest

  const syncCol = Math.round(bufW * 0.80);
  const bit0Col = Math.round(bufW * 0.87);
  const bit1Col = Math.round(bufW * 0.94);

  const timeline = [];
  [{ c: syncCol, n: 6 }, { c: bit1Col, n: 3 }, { c: bit0Col, n: 3 }, { c: bit1Col, n: 3 },
   { c: bit1Col, n: 3 }, { c: bit0Col, n: 3 }, { c: bit1Col, n: 3 }, { c: bit0Col, n: 3 },
   { c: bit0Col, n: 3 }, { c: bit1Col, n: 3 }]
    .forEach((p) => { for (let k = 0; k < p.n; k++) timeline.push(p.c); });
  const gapFrames = 14;
  const cycleLen = timeline.length + gapFrames;

  let frame = 0;

  function colormap(v) {
    v = Math.min(1, Math.max(0, v));
    const stops = [
      { p: 0.0, c: [7, 9, 10] },
      { p: 0.35, c: [13, 42, 46] },
      { p: 0.68, c: [32, 118, 112] },
      { p: 1.0, c: [150, 255, 225] },
    ];
    for (let i = 0; i < stops.length - 1; i++) {
      if (v >= stops[i].p && v <= stops[i + 1].p) {
        const t = (v - stops[i].p) / (stops[i + 1].p - stops[i].p);
        const a = stops[i].c, b = stops[i + 1].c;
        return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
      }
    }
    return stops[stops.length - 1].c;
  }

  function newRow(f) {
    const row = new Float32Array(bufW);
    for (let i = 0; i < bufW; i++) {
      const pos = i / bufW;
      if (pos < 0.72) {
        row[i] = 0.10 + 0.30 * Math.abs(Math.sin(pos * 11 + f * 0.09)) * (0.55 + 0.45 * Math.sin(f * 0.05 + i * 0.3));
        row[i] += Math.random() * 0.05;
      } else {
        row[i] = Math.random() * 0.035;
      }
    }
    const cyclePos = f % cycleLen;
    if (cyclePos < timeline.length) {
      const col = timeline[cyclePos];
      row[col] = 0.85 + Math.random() * 0.15;
      if (col > 0) row[col - 1] = Math.max(row[col - 1], 0.3);
      if (col < bufW - 1) row[col + 1] = Math.max(row[col + 1], 0.3);
    }
    return row;
  }

  const off = document.createElement("canvas");
  off.width = bufW;
  off.height = bufH;
  const offCtx = off.getContext("2d");
  const imgData = offCtx.createImageData(bufW, bufH);

  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
  }
  resize();
  window.addEventListener("resize", resize);

  let last = 0;
  function step(ts) {
    if (ts - last > 65) {
      last = ts;
      buffer.copyWithin(bufW, 0, bufW * (bufH - 1));
      buffer.set(newRow(frame), 0);
      frame++;

      for (let r = 0; r < bufH; r++) {
        for (let c = 0; c < bufW; c++) {
          const v = buffer[r * bufW + c];
          const [rr, gg, bb] = colormap(v);
          const idx = (r * bufW + c) * 4;
          imgData.data[idx] = rr;
          imgData.data[idx + 1] = gg;
          imgData.data[idx + 2] = bb;
          imgData.data[idx + 3] = 255;
        }
      }
      offCtx.putImageData(imgData, 0, 0);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(off, 0, 0, bufW, bufH, 0, 0, canvas.width, canvas.height);
    }
    requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function initLandingInteractions() {
  const items = document.querySelectorAll(".stack-item");
  const title = document.getElementById("stackPreviewTitle");
  const copy = document.getElementById("stackPreviewCopy");
  const number = document.querySelector(".stack-preview-number");
  if (!items.length || !title || !copy || !number) return;

  const phases = {
    message: ["01", "A thought becomes a payload.", "Plain text enters the encoder, ready to travel somewhere the ear does not naturally look."],
    encrypt: ["02", "A private shape for the signal.", "The receiver's public key gives the bytes a layer that only the matching private key can undo."],
    modulate: ["03", "Characters become frequency.", "The payload becomes a sequence of tones, each one precise enough to be found again."],
    embed: ["04", "The carrier keeps playing.", "The ultrasonic layer slips into the host track while everything familiar stays familiar."],
    recover: ["05", "The hidden becomes legible.", "A sweep finds the sync beacon, reads the bits, checks the message, and brings it back."],
  };

  items.forEach((item) => item.addEventListener("click", () => {
    const phase = phases[item.dataset.stack];
    if (!phase) return;
    items.forEach((node) => node.classList.toggle("active", node === item));
    number.textContent = phase[0];
    title.textContent = phase[1];
    copy.textContent = phase[2];
  }));
}

// ============================================================================
// ENCODE PAGE
// ============================================================================
function initEncodePage() {
  const form = document.getElementById("encodeForm");
  if (!form) return;

  const dropzone = document.getElementById("encodeDropzone");
  const input = document.getElementById("audioInput");
  const filenameEl = document.getElementById("dzFilename");
  const demoRow = document.getElementById("demoChipRow");
  const messageInput = document.getElementById("messageInput");
  const charCount = document.getElementById("charCount");
  const publicKeyInput = document.getElementById("publicKeyInput");
  const amplitudeInput = document.getElementById("amplitudeInput");
  const ampValue = document.getElementById("ampValue");
  const submitBtn = document.getElementById("encodeSubmit");
  const resultBody = document.getElementById("resultBody");
  const resultTag = document.getElementById("resultTag");
  const progressEl = document.getElementById("encodeProgress");

  let selectedDemoTrack = null;

  attachDropzone(dropzone, input, filenameEl, () => {
    selectedDemoTrack = null;
    demoRow.querySelectorAll(".demo-chip").forEach((c) => c.classList.remove("selected"));
  });

  demoRow.querySelectorAll(".demo-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      demoRow.querySelectorAll(".demo-chip").forEach((c) => c.classList.remove("selected"));
      chip.classList.add("selected");
      selectedDemoTrack = chip.dataset.file;
      input.value = "";
      filenameEl.textContent = "";
    });
  });

  messageInput.addEventListener("input", () => {
    const bytes = new TextEncoder().encode(messageInput.value).length;
    charCount.textContent = bytes;
  });

  amplitudeInput.addEventListener("input", () => {
    ampValue.textContent = parseFloat(amplitudeInput.value).toFixed(3);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const message = messageInput.value.trim();
    if (!message) { toast("Type a message to hide first."); return; }
    if (!input.files[0] && !selectedDemoTrack) { toast("Pick an audio file or a demo track."); return; }
    if (input.files[0] && input.files[0].size > MAX_UPLOAD_BYTES) { toast(uploadSizeMessage(input.files[0])); return; }

    const fd = new FormData();
    if (input.files[0]) fd.append("audio", input.files[0]);
    else fd.append("demo_track", selectedDemoTrack);
    fd.append("message", message);
    if (!publicKeyInput.value.trim()) { toast("Paste the receiver public key first."); return; }
    fd.append("public_key", publicKeyInput.value);
    fd.append("amplitude", amplitudeInput.value);

    submitBtn.disabled = true;
    submitBtn.textContent = "Embedding…";
    resultTag.textContent = "PROCESSING";

    const req = fetch("/api/encode", { method: "POST", body: fd }).then((r) => r.json());
    const data = await runProgress(progressEl, ["encrypt", "modulate", "embed", "done"], req);

    submitBtn.disabled = false;
    submitBtn.textContent = "Embed watermark";

    if (data.error) {
      resultTag.textContent = "ERROR";
      resultBody.innerHTML = `<div class="banner bad">${escapeHtml(data.error)}</div>`;
      return;
    }

    resultTag.textContent = "WATERMARKED";
    renderEncodeResult(resultBody, data);
    toast("Watermark embedded — listen for yourself below.");
  });
}

function renderEncodeResult(container, data) {
  const s = data.stats;
  container.innerHTML = `
    <div class="banner ok">
      <span>Embedded ${s.payload_bytes} bytes across ${s.total_bits} bits, tiled ${s.repeats_embedded}× through the track. Processed in ${s.processing_seconds}s.</span>
    </div>
    <div class="stat-grid">
      <div class="stat-cell"><b>${s.output_duration.toFixed(1)}s</b><span>OUTPUT LENGTH</span></div>
      <div class="stat-cell"><b>${s.repeats_embedded}×</b><span>FRAME REPEATS</span></div>
      <div class="stat-cell"><b>${Math.round(s.bit_rate_bps)} bps</b><span>DATA RATE</span></div>
      <div class="stat-cell"><b>${(data.sync_freq/1000).toFixed(1)}kHz</b><span>SYNC BEACON</span></div>
    </div>

    <div class="viz-block">
      <h4>Waveform — before (grey) vs after (cyan outline)</h4>
      <div class="viz-canvas-wrap"><canvas id="wfCompareCanvas"></canvas></div>
    </div>

    <div class="viz-block">
      <h4>Spectrum of the watermarked file</h4>
      <div class="viz-canvas-wrap"><canvas id="spectrumCanvas"></canvas></div>
    </div>

    <div class="audio-block">
      <h4 style="margin:0 0 8px;color:var(--ink-dim);font-size:11.5px;">Listen — one version at a time</h4>
      <div class="audio-compare">
        <div class="audio-card">
          <div class="lbl">ORIGINAL</div>
          <audio controls preload="metadata" src="${data.original_url}"></audio>
        </div>
        <div class="audio-card">
          <div class="lbl">WATERMARKED</div>
          <audio controls preload="metadata" src="${data.download_url}"></audio>
        </div>
      </div>
    </div>

    <a href="${data.download_url}" class="btn btn-primary btn-block" style="margin-top:18px;" download>Download watermarked file</a>
  `;
  drawWaveformCompare(document.getElementById("wfCompareCanvas"), data.waveform_before, data.waveform_after);
  drawSpectrum(document.getElementById("spectrumCanvas"), data.spectrum.freqs, data.spectrum.db, data.watermark_band, data.sync_freq);

  const comparePlayers = [...container.querySelectorAll("audio")];
  comparePlayers.forEach((player) => {
    player.addEventListener("play", () => {
      // Keep A/B listening sequential without disabling either control.
      comparePlayers.forEach((other) => {
        if (other !== player && !other.paused) other.pause();
      });
    });
    player.addEventListener("error", () => {
      toast("This audio version could not be loaded. Try pressing play again.");
    });
  });
}

// ============================================================================
// DECODE PAGE
// ============================================================================
function initDecodePage() {
  const form = document.getElementById("decodeForm");
  if (!form) return;

  const dropzone = document.getElementById("decodeDropzone");
  const input = document.getElementById("decodeAudioInput");
  const filenameEl = document.getElementById("decodeDzFilename");
  const privateKeyInput = document.getElementById("privateKeyInput");
  const submitBtn = document.getElementById("decodeSubmit");
  const resultBody = document.getElementById("decodeResultBody");
  const resultTag = document.getElementById("decodeResultTag");
  const progressEl = document.getElementById("decodeProgress");

  attachDropzone(dropzone, input, filenameEl, null);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!input.files[0]) { toast("Drop a file to scan first."); return; }
    if (input.files[0].size > MAX_UPLOAD_BYTES) { toast(uploadSizeMessage(input.files[0])); return; }

    const fd = new FormData();
    fd.append("audio", input.files[0]);
    if (!privateKeyInput.value.trim()) { toast("Paste the receiver private key first."); return; }
    fd.append("private_key", privateKeyInput.value);

    submitBtn.disabled = true;
    submitBtn.textContent = "Scanning…";
    resultTag.textContent = "SCANNING";

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const req = fetch("/api/decode", { method: "POST", body: fd, signal: controller.signal }).then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok && !data.error) {
          data.error = `The decoder server returned HTTP ${response.status}.`;
        }
        return data;
      });
      const data = await runProgress(progressEl, ["scan", "sync", "demod", "done"], req);

      if (data.error) {
        resultTag.textContent = "ERROR";
        resultBody.innerHTML = `<div class="banner bad">${escapeHtml(data.error)}</div>`;
        return;
      }

      resultTag.textContent = data.success ? "MESSAGE FOUND" : "NOT FOUND";
      await renderDecodeResult(resultBody, data);
    } catch (error) {
      resultTag.textContent = "ERROR";
      const message = error.name === "AbortError"
        ? "Decoding timed out after 90 seconds. Try a shorter audio file."
        : (error.message || "The decode request failed. Check that the server is running and try again.");
      resultBody.innerHTML = `<div class="banner bad">${escapeHtml(message)}</div>`;
    } finally {
      clearTimeout(timeout);
      submitBtn.disabled = false;
      submitBtn.textContent = "Scan for watermark";
    }
  });
}

async function renderDecodeResult(container, data) {
  const gaugeColor = data.success ? "#57e8d1" : "#ffb454";
  container.innerHTML = `
    <div class="gauge-row">
      ${gaugeSVG(data.confidence, gaugeColor)}
      <div class="gauge-copy">
        <b>${data.confidence.toFixed(1)}%</b>
        <span>DETECTION CONFIDENCE</span>
      </div>
    </div>

    <div class="viz-block">
      <h4>Spectrum sweep of uploaded file</h4>
      <div class="viz-canvas-wrap"><canvas id="decodeSpectrumCanvas"></canvas></div>
    </div>

    <div class="viz-block">
      <h4>Waveform</h4>
      <div class="viz-canvas-wrap"><canvas id="decodeWaveformCanvas"></canvas></div>
    </div>

    <div id="decodeMessageArea"></div>
  `;
  drawSpectrum(document.getElementById("decodeSpectrumCanvas"), data.spectrum.freqs, data.spectrum.db, data.watermark_band, data.sync_freq);
  drawWaveformSingle(document.getElementById("decodeWaveformCanvas"), data.waveform, "#57e8d1");

  const area = document.getElementById("decodeMessageArea");
  if (data.success) {
    area.innerHTML = `
      <div class="stat-grid">
        <div class="stat-cell"><b>${data.payload_bytes}</b><span>PAYLOAD BYTES</span></div>
        <div class="stat-cell"><b>${data.matched_offset_seconds.toFixed(2)}s</b><span>FRAME OFFSET</span></div>
        <div class="stat-cell"><b>${data.snr_db.toFixed(1)}dB</b><span>SIGNAL/NOISE</span></div>
        <div class="stat-cell"><b>${data.processing_seconds}s</b><span>SCAN TIME</span></div>
      </div>
      <h4 style="margin-bottom:8px;color:var(--ink-dim);font-size:11.5px;">Recovered message</h4>
      <div class="terminal"><span id="typedMsg"></span><span class="cursor"></span></div>
    `;
    await typeWriter(document.getElementById("typedMsg"), data.message, 14);
  } else {
    area.innerHTML = `<div class="banner ${data.confidence > 20 ? 'bad' : 'info'}">${escapeHtml(data.reason || "No watermark could be recovered.")}</div>`;
  }
}

// ============================================================================
// DASHBOARD
// ============================================================================
function initDashboard() {
  document.querySelectorAll(".meter").forEach((meter) => {
    const value = parseFloat(meter.dataset.value) || 0;
    const max = parseFloat(meter.dataset.max) || 100;
    const hot = meter.dataset.hot === "1";
    const bars = meter.querySelector(".bars");
    const total = 14;
    const lit = Math.round((Math.min(value, max) / max) * total);
    let html = "";
    for (let i = 0; i < total; i++) {
      const isLit = i < lit;
      const isHot = hot && i >= total - 3;
      html += `<i class="${isLit ? "lit" : ""}${isLit && isHot ? " hot" : ""}"></i>`;
    }
    bars.innerHTML = html;
  });
}

// ---------------------------------------------------------------- helpers --
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ------------------------------------------------------------- dispatcher --
document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "home") { initHero(); initLandingInteractions(); }
  if (page === "encode") initEncodePage();
  if (page === "decode") initDecodePage();
  if (page === "dashboard") initDashboard();
});
