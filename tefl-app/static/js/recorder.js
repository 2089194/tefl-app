(function () {
  "use strict";

  const recordBtn   = document.getElementById("record-btn");
  if (!recordBtn) return;

  const iconMic     = document.getElementById("icon-mic");
  const iconStop    = document.getElementById("icon-stop");
  const timerEl     = document.getElementById("timer");
  const labelEl     = document.getElementById("record-label");
  const waveform    = document.getElementById("waveform");
  const viewRecord  = document.getElementById("view-record");
  const viewProcess = document.getElementById("view-processing");
  const viewError   = document.getElementById("view-error");

  let isRecording = false, mediaRecorder = null, audioChunks = [];
  let timerRef = null, secondsElapsed = 0;
  let audioCtx = null, analyser = null, animFrame = null;

  function fmt(s){ return `${Math.floor(s/60)}:${(s%60).toString().padStart(2,'0')}`; }

  function setRecording(active){
    isRecording = active;
    recordBtn.classList.toggle("record-btn--recording", active);
    iconMic.style.display  = active ? "none"  : "block";
    iconStop.style.display = active ? "block" : "none";
    if(timerEl) timerEl.classList.toggle("record-timer--recording", active);
    if(labelEl) labelEl.textContent = active ? "Tap to Stop" : "Tap to Start Speaking";
    if(waveform) waveform.classList.toggle("waveform--active", active);
  }

  function startTimer(){
    secondsElapsed = 0;
    if(timerEl) timerEl.textContent = fmt(0);
    timerRef = setInterval(()=>{
      secondsElapsed++;
      if(timerEl) timerEl.textContent = fmt(secondsElapsed);
      if(secondsElapsed >= 60) stopRecording();
    }, 1000);
  }

  function stopTimer(){ clearInterval(timerRef); timerRef = null; }

  function startWaveform(stream){
    if(!waveform) return;
    const bars = waveform.querySelectorAll(".waveform__bar");
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      audioCtx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      (function draw(){
        animFrame = requestAnimationFrame(draw);
        analyser.getByteFrequencyData(data);
        bars.forEach((b,i)=>{
          const v = data[Math.floor(i/bars.length*data.length)]/255;
          b.style.height = `${Math.max(10, v*80)}%`;
        });
      })();
    } catch(e){ /* CSS animation fallback */ }
  }

  function stopWaveform(){
    if(animFrame){ cancelAnimationFrame(animFrame); animFrame=null; }
    if(audioCtx){ audioCtx.close().catch(()=>{}); audioCtx=null; }
    waveform && waveform.querySelectorAll(".waveform__bar").forEach((b,i)=>{ b.style.height=`${Math.abs(Math.sin(i*0.5))*30+10}%`; });
  }

  async function startRecording(){
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio:true});
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = e => { if(e.data.size>0) audioChunks.push(e.data); };
      mediaRecorder.onstop = () => { stream.getTracks().forEach(t=>t.stop()); onRecordingDone(); };
      mediaRecorder.start(100);
      setRecording(true);
      startTimer();
      startWaveform(stream);
    } catch(err){
      console.error(err);
      viewRecord && (viewRecord.style.display="none");
      viewError  && (viewError.style.display="block");
    }
  }

  function stopRecording(){
    if(mediaRecorder && mediaRecorder.state !== "inactive"){
      mediaRecorder.stop();
      stopTimer();
      stopWaveform();
      setRecording(false);
      viewRecord  && (viewRecord.style.display="none");
      viewProcess && (viewProcess.style.display="block");
    }
  }

  async function onRecordingDone(){
    const blob = new Blob(audioChunks, {type:"audio/webm"});
    try {
      const fd = new FormData();
      fd.append("audio", blob, "recording.webm");
      const r1 = await fetch("/api/transcribe", {method:"POST", body:fd});
      const d1 = await r1.json();

      const r2 = await fetch("/api/feedback",   {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({transcript:d1.transcript})});
      await r2.json();

      // Sprint 2: redirect to feedback page with real data
      window.location.href = "/feedback";
    } catch(e){
      console.error(e);
      window.location.href = "/feedback"; // still navigate on error for now
    }
  }

  recordBtn.addEventListener("click", ()=>{
    if(isRecording) stopRecording(); else startRecording();
  });
})();
