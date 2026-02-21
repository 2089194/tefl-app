"""
app.py – tefll-app Flask application
Sprint 3: Ollama AI feedback integrated into /api/feedback
          Real transcript + scores passed through to feedback screen
"""

import os
import json
import logging
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
OLLAMA_MODEL  = os.environ.get("OLLAMA_MODEL",  "llama3.2")

# ── Static data (Sprint 4: replace with DB) ───────────────────
PROMPTS = [
    {"title": "Describe your weekend",       "description": "Talk about what you did last weekend"},
    {"title": "Talk about your studies",     "description": "Share about your academic interests"},
    {"title": "Describe a recent challenge", "description": "Explain a difficulty you overcame"},
]

PAST_SESSIONS = [
    {"prompt_title": "Describe your weekend",       "date": "18 Feb 2026", "pronunciation_score": 82, "fluency_score": 75, "grammar_score": 68},
    {"prompt_title": "Talk about your studies",     "date": "17 Feb 2026", "pronunciation_score": 78, "fluency_score": 80, "grammar_score": 72},
    {"prompt_title": "Describe a recent challenge", "date": "16 Feb 2026", "pronunciation_score": 74, "fluency_score": 71, "grammar_score": 75},
]

# ── Fallback feedback (shown if Ollama is unavailable) ────────
FALLBACK_FEEDBACK = {
    "prompt_title":        "Free Practice",
    "transcript":          "No transcript available.",
    "pronunciation":       0,
    "fluency":             0,
    "grammar":             0,
    "overall_comment":     "AI feedback is currently unavailable. Please ensure Ollama is running.",
    "pronunciation_items": [],
    "grammar_items":       [],
    "filler_words":        [],
    "improved_version":    "",
    "improved_full":       "",
    "ollama_ok":           False,
}

# ── Onboarding ────────────────────────────────────────────────
@app.route("/onboarding/")
def onboarding_welcome():
    return render_template("onboarding_welcome.html", show_nav=False)

@app.route("/onboarding/how-it-works")
def onboarding_how():
    return render_template("onboarding_how.html", show_nav=False)

@app.route("/onboarding/privacy")
def onboarding_privacy():
    return render_template("onboarding_privacy.html", show_nav=False)

# ── Main screens ──────────────────────────────────────────────
@app.route("/")
def index():
    stats = {
        "sessions_this_week": len(PAST_SESSIONS),
        "avg_score": int(sum(
            (s["pronunciation_score"] + s["fluency_score"] + s["grammar_score"]) / 3
            for s in PAST_SESSIONS
        ) / len(PAST_SESSIONS)) if PAST_SESSIONS else 0,
        "streak": min(len(PAST_SESSIONS), 7),
    }
    return render_template("home.html", stats=stats, prompts=PROMPTS,
                           user_name="Learner", show_nav=True, active="home")

@app.route("/speak")
def speak():
    prompt_title = request.args.get("prompt", "Free Practice")
    return render_template("speaking.html", prompt_title=prompt_title,
                           show_nav=True, active="speaking")

@app.route("/feedback")
def feedback():
    # Pull real feedback data from session if available
    feedback_data = session.pop("last_feedback", None)

    if feedback_data:
        # Map API response keys to template keys
        display = {
            "prompt_title":        feedback_data.get("prompt_title", "Free Practice"),
            "transcript":          feedback_data.get("transcript", ""),
            "pronunciation":       feedback_data.get("pronunciation_score", 0),
            "fluency":             feedback_data.get("fluency_score", 0),
            "grammar":             feedback_data.get("grammar_score", 0),
            "overall_comment":     feedback_data.get("overall_comment", ""),
            "pronunciation_items": feedback_data.get("pronunciation_items", []),
            "grammar_items":       feedback_data.get("grammar_items", []),
            "filler_words":        feedback_data.get("filler_words", []),
            "improved_version":    feedback_data.get("improved_version", ""),
            "improved_full":       feedback_data.get("improved_full", ""),
            "ollama_ok":           feedback_data.get("ollama_ok", False),
        }
    else:
        display = FALLBACK_FEEDBACK

    return render_template("feedback.html", feedback=display,
                           show_nav=True, active="feedback")

@app.route("/history")
def history():
    return render_template("history.html", past_sessions=PAST_SESSIONS,
                           show_nav=True, active="history")

@app.route("/profile")
def profile():
    return render_template("profile.html",
        user_name="Learner", user_email="", native_language="Korean",
        english_level="Intermediate", show_nav=True, active="profile")

# ── API: Transcription (Whisper) ──────────────────────────────
@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "No audio file received", "transcript": ""}), 400

    audio_bytes = audio_file.read()
    if len(audio_bytes) < 1000:
        return jsonify({"error": "Audio too short", "transcript": ""}), 400

    try:
        from whisper_stt import transcribe_audio, get_model_name
        model_name = get_model_name()
        logger.info(f"Transcribing {len(audio_bytes)} bytes with Whisper ({model_name})...")
        result = transcribe_audio(audio_bytes, model_name=model_name)

        if result["error"]:
            return jsonify({
                "transcript": "", "language": "unknown",
                "whisper_available": True, "error": result["error"],
            }), 500

        logger.info(f"Transcript: {result['transcript'][:120]}")
        return jsonify({
            "transcript":        result["transcript"],
            "language":          result["language"],
            "segments":          result["segments"],
            "whisper_available": True,
            "error":             None,
        })

    except RuntimeError as e:
        return jsonify({
            "transcript": "", "language": "unknown",
            "whisper_available": False, "error": str(e),
        }), 503

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return jsonify({
            "transcript": "", "language": "unknown",
            "whisper_available": True, "error": str(e),
        }), 500


# ── API: Feedback (Ollama) ────────────────────────────────────
@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """
    Receives { transcript, prompt_title } JSON.
    Sends transcript to Ollama, returns structured feedback JSON.
    Also stores result in Flask session so /feedback can display it.
    """
    data         = request.get_json(silent=True) or {}
    transcript   = data.get("transcript", "").strip()
    prompt_title = data.get("prompt_title", "Free Practice")

    logger.info(f"Feedback requested for: '{transcript[:80]}...'")

    if not transcript:
        return jsonify({"error": "No transcript provided"}), 400

    try:
        from ollama_feedback import generate_feedback
        feedback = generate_feedback(transcript)
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        feedback = {
            "pronunciation_score": 0, "fluency_score": 0, "grammar_score": 0,
            "overall_comment": "AI feedback unavailable.",
            "pronunciation_items": [], "grammar_items": [],
            "filler_words": [], "improved_version": transcript,
            "improved_full": transcript,
            "transcript": transcript, "ollama_ok": False, "error": str(e),
        }

    feedback["prompt_title"] = prompt_title

    # Store in session so /feedback route can display it
    session["last_feedback"] = feedback

    return jsonify({
        "status":              "ok",
        "pronunciation_score": feedback.get("pronunciation_score", 0),
        "fluency_score":       feedback.get("fluency_score", 0),
        "grammar_score":       feedback.get("grammar_score", 0),
        "ollama_ok":           feedback.get("ollama_ok", False),
        "error":               feedback.get("error"),
    })


# ── API: Status ───────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    """Check Whisper and Ollama status."""
    # Whisper
    try:
        import whisper
        whisper_ok = True
    except ImportError:
        whisper_ok = False

    # Ollama
    try:
        from ollama_feedback import check_ollama
        ollama_status = check_ollama()
    except Exception as e:
        ollama_status = {"ollama_running": False, "error": str(e)}

    return jsonify({
        "whisper_installed":  whisper_ok,
        "whisper_model":      WHISPER_MODEL,
        "ffmpeg_note":        "Run 'ffmpeg -version' to verify",
        **ollama_status,
    })


if __name__ == "__main__":
    app.run(debug=True)
