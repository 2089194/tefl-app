"""
app.py – tefl-app Flask application
Sprint 2: Whisper STT integrated into /api/transcribe
"""

import os
import logging
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# ── Whisper model (lazy-loaded on first request) ──────────────
# Set WHISPER_MODEL=tiny in .env for faster loading during dev
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")

# ── Shared data (Sprint 3: replace with DB queries) ──────────
PROMPTS = [
    {"title": "Describe your weekend",       "description": "Talk about what you did last weekend"},
    {"title": "Talk about your studies",     "description": "Share about your academic interests"},
    {"title": "Describe a recent challenge", "description": "Explain a difficulty you overcame"},
]

PLACEHOLDER_FEEDBACK = {
    "prompt_title":   "Describe your weekend",
    "transcript":     "Last weekend I go to the park with my friend. We have very good time. The weather was beautiful and we take many photos.",
    "pronunciation":  76,
    "fluency":        80,
    "grammar":        68,
    "pronunciation_items": [
        {"word": "beautiful",   "issue": "Stress on wrong syllable", "correction": "BEAU-ti-ful",    "phonetic": "/ˈbjuːtɪfəl/"},
        {"word": "comfortable", "issue": "Missing syllable",          "correction": "COM-for-ta-ble", "phonetic": "/ˈkʌmfətəbəl/"},
    ],
    "grammar_items": [
        {"incorrect": "I go to the park",      "correct": "I went to the park",      "explanation": "Use past tense when describing past events.",       "example": "Yesterday, I walked to school."},
        {"incorrect": "We have very good time", "correct": "We had a very good time", "explanation": 'Past tense verb and article "a" are needed.',       "example": "They had a great party."},
    ],
    "filler_words":    ["um", "like"],
    "improved_version": "Last weekend, I went to the park with my friend. We had a wonderful time.",
    "improved_full":    "Last weekend, I went to the park with my friend. We had a very good time.\nThe weather was beautiful, and we took many photos.\nIt was a perfect way to spend a relaxing afternoon.",
}

PAST_SESSIONS = [
    {"prompt_title": "Describe your weekend",       "date": "18 Feb 2026", "pronunciation_score": 82, "fluency_score": 75, "grammar_score": 68},
    {"prompt_title": "Talk about your studies",     "date": "17 Feb 2026", "pronunciation_score": 78, "fluency_score": 80, "grammar_score": 72},
    {"prompt_title": "Describe a recent challenge", "date": "16 Feb 2026", "pronunciation_score": 74, "fluency_score": 71, "grammar_score": 75},
]

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
    # Sprint 3: pull real session data from DB using session ID
    return render_template("feedback.html", feedback=PLACEHOLDER_FEEDBACK,
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
    """
    Receives audio blob from the browser recorder.
    Returns JSON: { transcript, language, whisper_available, error }
    """
    audio_file = request.files.get("audio")

    if not audio_file:
        return jsonify({"error": "No audio file received", "transcript": ""}), 400

    audio_bytes = audio_file.read()

    if len(audio_bytes) < 1000:
        return jsonify({"error": "Audio too short", "transcript": ""}), 400

    # Try to use Whisper; fall back gracefully if not installed
    try:
        from whisper_stt import transcribe_audio, get_model_name
        model_name = get_model_name()
        logger.info(f"Transcribing {len(audio_bytes)} bytes with Whisper ({model_name})...")
        result = transcribe_audio(audio_bytes, model_name=model_name)

        if result["error"]:
            logger.error(f"Whisper error: {result['error']}")
            return jsonify({
                "transcript": "",
                "language": "unknown",
                "whisper_available": True,
                "error": result["error"],
            }), 500

        logger.info(f"Transcript: {result['transcript'][:100]}...")
        return jsonify({
            "transcript":         result["transcript"],
            "language":           result["language"],
            "segments":           result["segments"],
            "whisper_available":  True,
            "error":              None,
        })

    except RuntimeError as e:
        # Whisper not installed
        logger.warning(f"Whisper not available: {e}")
        return jsonify({
            "transcript":        "Whisper is not installed. Run: pip install openai-whisper",
            "language":          "unknown",
            "whisper_available": False,
            "error":             str(e),
        }), 503

    except Exception as e:
        logger.error(f"Unexpected transcription error: {e}")
        return jsonify({
            "transcript": "",
            "language":   "unknown",
            "whisper_available": True,
            "error": str(e),
        }), 500


# ── API: Feedback (Sprint 3: wire to Ollama) ──────────────────
@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """
    Receives transcript JSON.
    Returns placeholder scores for now.
    Sprint 3: pipe transcript through Ollama for real AI feedback.
    """
    data = request.get_json(silent=True) or {}
    transcript = data.get("transcript", "")
    logger.info(f"Feedback requested for transcript: {transcript[:80]}...")

    # Placeholder — Sprint 3 replaces this with Ollama
    return jsonify({
        "pronunciation":   76,
        "fluency":         80,
        "grammar":         68,
        "filler_words":    ["um", "like"],
        "improved_version": "Placeholder — Ollama feedback coming in Sprint 3.",
        "status":          "ok",
        "transcript":      transcript,
    })


# ── Dev helper: check Whisper status ─────────────────────────
@app.route("/api/status")
def api_status():
    """Quick endpoint to check if Whisper is installed and working."""
    try:
        import whisper
        return jsonify({
            "whisper_installed": True,
            "model_configured":  WHISPER_MODEL,
            "ffmpeg_note":       "Make sure ffmpeg is installed and on your PATH",
        })
    except ImportError:
        return jsonify({
            "whisper_installed": False,
            "install_command":   "pip install openai-whisper",
            "ffmpeg_note":       "Also install ffmpeg: winget install ffmpeg",
        })


if __name__ == "__main__":
    app.run(debug=True)
