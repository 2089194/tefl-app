// tefl app – recorder.js
// Handles the full recording lifecycle on the Speaking Task screen.
// Sprint 1: UI state machine + MediaRecorder plumbing.
// Sprint 2: wire audioBlob → /api/transcribe → /api/feedback.

(function () {
  "use strict";

  // ── DOM refs ─────────────────────────────────────────────
  const recordBtn       = document.getElementById("record-btn");
  const recorderEl      = document.getElementById("recorder");
  const timerEl         = document.getElementById("timer");
  const hintEl          = document.getElementById("recorder-hint");
  const waveformBars    = document.getElementById("waveform-bars");
  const waveformPlaceholder = document.getElementById("waveform-placeholder");
  const resultsPreview  = document.getElementById("results-preview");
  const retryBtn        = document.getElementById("retry-btn");

  if (!recordBtn) return; // not on speaking screen

  // ── State ────────────────────────────────────────────────
  let state = "idle"; // "idle" | "recording" | "done"
  let mediaRecorder = null;
  let audioChunks = [];
  let audioBlob = null;
  let timerInterval = null;
  let secondsElapsed = 0;
  let analyserNode = null;
  let animFrameId = null;
  let audioCtx = null;

  // ── Helpers ──────────────────────────────────────────────
  function formatTime(s) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  }

  function setState(next) {
    state = next;
    recordBtn.dataset.state = next;
    recordBtn.setAttribute(
      "aria-label",
      next === "recording" ? "Stop recording" : "Start recording"
    );

    if (next === "recording") {
      recordBtn.classList.add("record-btn--recording");
      recorderEl.classList.add("recorder--recording");
      hintEl.textContent = "Tap to stop recording";
      waveformPlaceholder && (waveformPlaceholder.hidden = true);
      waveformBars && (waveformBars.hidden = false);
      resultsPreview && (resultsPreview.hidden = true);
    } else if (next === "done") {
      recordBtn.classList.remove("record-btn--recording");
      recorderEl.classList.remove("recorder--recording");
      hintEl.textContent = "Recording complete";
      stopAnimatedBars();
    } else {
      // idle
      recordBtn.classList.remove("record-btn--recording");
      recorderEl.classList.remove("recorder--recording");
      hintEl.textContent = "Tap to start recording";
      waveformPlaceholder && (waveformPlaceholder.hidden = false);
      waveformBars && (waveformBars.hidden = true);
      resultsPreview && (resultsPreview.hidden = true);
      timerEl.textContent = "0:00";
    }
  }

  // ── Timer ────────────────────────────────────────────────
  function startTimer() {
    secondsElapsed = 0;
    timerEl.textContent = formatTime(0);
    timerInterval = setInterval(() => {
      secondsElapsed++;
      timerEl.textContent = formatTime(secondsElapsed);
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
  }

  // ── Waveform animation via AnalyserNode ──────────────────
  function startAnimatedBars(stream) {
    if (!waveformBars) return;
    const bars = waveformBars.querySelectorAll(".waveform__bar");

    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      analyserNode = audioCtx.createAnalyser();
      analyserNode.fftSize = 64;
      source.connect(analyserNode);

      const dataArray = new Uint8Array(analyserNode.frequencyBinCount);

      function draw() {
        animFrameId = requestAnimationFrame(draw);
        analyserNode.getByteFrequencyData(dataArray);
        bars.forEach((bar, i) => {
          const idx = Math.floor((i / bars.length) * dataArray.length);
          const val = dataArray[idx] / 255;
          const h = Math.max(6, val * 48);
          bar.style.height = `${h}px`;
        });
      }
      draw();
    } catch {
      // AudioContext unavailable – CSS animation fallback via class
    }
  }

  function stopAnimatedBars() {
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
    if (audioCtx) {
      audioCtx.close().catch(() => {});
      audioCtx = null;
    }
    // Reset bar heights
    if (waveformBars) {
      const bars = waveformBars.querySelectorAll(".waveform__bar");
      bars.forEach((bar, i) => {
        const h = Math.abs(Math.sin(i * 0.5)) * 16 + 8;
        bar.style.height = `${h}px`;
      });
    }
  }

  // ── Recording ────────────────────────────────────────────
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        stream.getTracks().forEach((t) => t.stop());
        handleRecordingDone(audioBlob);
      };

      mediaRecorder.start(100); // collect chunks every 100ms
      startAnimatedBars(stream);
      startTimer();
      setState("recording");
    } catch (err) {
      console.error("Microphone access denied:", err);
      alert(
        "Microphone access is required for recording. Please allow access and try again."
      );
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      stopTimer();
      setState("done");
    }
  }

  // ── Post-recording: stub API calls ───────────────────────
  // Sprint 2: replace stubs with real Whisper + Ollama responses.
  async function handleRecordingDone(blob) {
    // Show placeholder scores immediately
    showQuickScores({ overall: "…", pronunciation: "…", fluency: "…" });
    resultsPreview && (resultsPreview.hidden = false);

    try {
      // --- Transcription stub ---
      const formData = new FormData();
      formData.append("audio", blob, "recording.webm");

      const transcribeRes = await fetch("/api/transcribe", {
        method: "POST",
        body: formData,
      });
      const transcribeData = await transcribeRes.json();

      // --- Feedback stub ---
      const feedbackRes = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: transcribeData.transcript }),
      });
      const feedbackData = await feedbackRes.json();

      showQuickScores(feedbackData);
    } catch (err) {
      console.error("API error:", err);
      showQuickScores({ overall: "—", pronunciation: "—", fluency: "—" });
    }
  }

  function showQuickScores(data) {
    const overall       = document.getElementById("qs-overall");
    const pronunciation = document.getElementById("qs-pronunciation");
    const fluency       = document.getElementById("qs-fluency");
    if (overall)       overall.textContent       = data.overall ?? "—";
    if (pronunciation) pronunciation.textContent = data.pronunciation ?? "—";
    if (fluency)       fluency.textContent        = data.fluency ?? "—";
    resultsPreview && (resultsPreview.hidden = false);
  }

  // ── Event listeners ──────────────────────────────────────
  recordBtn.addEventListener("click", () => {
    if (state === "idle")      startRecording();
    else if (state === "recording") stopRecording();
    else if (state === "done") setState("idle");
  });

  retryBtn && retryBtn.addEventListener("click", () => setState("idle"));

  // TTS button (stub – Sprint 2)
  const ttsBtn = document.getElementById("tts-btn");
  ttsBtn && ttsBtn.addEventListener("click", () => {
    const promptEl = document.querySelector(".prompt-text");
    if (!promptEl) return;
    if ("speechSynthesis" in window) {
      const utt = new SpeechSynthesisUtterance(
        promptEl.textContent.replace(/["""]/g, "").trim()
      );
      utt.lang = "en-GB";
      utt.rate = 0.9;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utt);
    }
  });

  // Initialise
  setState("idle");
})();
