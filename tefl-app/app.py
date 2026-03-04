"""
app.py - TEFL Speaking Feedback Tool
Sprint 6 - Railway deployment with Groq feedback API
"""

import os
import logging
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# ── Database configuration ────────────────────────────────────────────────────
# Railway provides DATABASE_URL automatically when Postgres plugin is added.
# Falls back to SQLite for local development.
database_url = os.environ.get("DATABASE_URL", "sqlite:///tefl_app.db")

# Railway uses postgres:// but SQLAlchemy requires postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

from models import db
db.init_app(app)

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
OLLAMA_MODEL  = os.environ.get("OLLAMA_MODEL",  "llama3.2")

PROMPTS = [
    {"title": "Describe your weekend",       "description": "Talk about what you did last weekend"},
    {"title": "Talk about your studies",     "description": "Share about your academic interests"},
    {"title": "Describe a recent challenge", "description": "Explain a difficulty you overcame"},
]

FALLBACK_FEEDBACK = {
    "prompt_title":        "Free Practice",
    "transcript":          "No transcript available.",
    "pronunciation":       0,
    "fluency":             0,
    "grammar":             0,
    "overall_comment":     "AI feedback is currently unavailable.",
    "pronunciation_items": [],
    "grammar_items":       [],
    "filler_words":        [],
    "improved_version":    "",
    "improved_full":       "",
    "ollama_ok":           False,
}


def init_db():
    with app.app_context():
        try:
            db.create_all()
            from db_helpers import get_or_create_default_user
            get_or_create_default_user()
            logger.info("Database ready.")
        except Exception as e:
            logger.warning(f"Database not available: {e}")
            logger.warning("Running without database — history will not be saved.")


# ── Onboarding ────────────────────────────────────────────────────────────────

@app.route("/onboarding/")
def onboarding_welcome():
    return render_template("onboarding_welcome.html", show_nav=False)

@app.route("/onboarding/how-it-works")
def onboarding_how():
    return render_template("onboarding_how.html", show_nav=False)

@app.route("/onboarding/privacy")
def onboarding_privacy():
    return render_template("onboarding_privacy.html", show_nav=False)


# ── Main screens ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    try:
        from db_helpers import get_home_stats
        stats = get_home_stats()
    except Exception:
        stats = {"sessions_this_week": 0, "avg_score": 0, "streak": 0}
    return render_template("home.html", stats=stats, prompts=PROMPTS,
                           user_name="Learner", show_nav=True, active="home")

@app.route("/speak")
def speak():
    prompt_title = request.args.get("prompt", "Free Practice")
    return render_template("speaking.html", prompt_title=prompt_title,
                           show_nav=True, active="speaking")

@app.route("/feedback")
def feedback():
    session_id = request.args.get("session_id")
    if session_id:
        try:
            from db_helpers import get_session_by_id
            s = get_session_by_id(int(session_id))
            if s:
                return render_template("feedback.html", feedback=s.to_feedback_dict(),
                                       show_nav=True, active="feedback")
        except Exception as e:
            logger.error(f"Error loading session {session_id}: {e}")

    feedback_data = session.pop("last_feedback", None)
    if feedback_data:
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
    try:
        from db_helpers import get_recent_sessions
        past_sessions = get_recent_sessions()
    except Exception as e:
        logger.warning(f"Could not load history: {e}")
        past_sessions = []
    return render_template("history.html", past_sessions=past_sessions,
                           show_nav=True, active="history")

@app.route("/profile")
def profile():
    return render_template("profile.html",
        user_name="Learner", user_email="", native_language="Korean",
        english_level="Intermediate", show_nav=True, active="profile")


# ── API: Transcription ────────────────────────────────────────────────────────

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
        result = transcribe_audio(audio_bytes, model_name=get_model_name())

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


# ── API: Feedback ─────────────────────────────────────────────────────────────

@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    data         = request.get_json(silent=True) or {}
    transcript   = data.get("transcript", "").strip()
    prompt_title = data.get("prompt_title", "Free Practice")

    if not transcript:
        return jsonify({"error": "No transcript provided"}), 400

    logger.info(f"Feedback requested for: '{transcript[:80]}...'")

    try:
        from ollama_feedback import generate_feedback
        feedback = generate_feedback(transcript)
    except Exception as e:
        logger.error(f"Feedback error: {e}")
        feedback = {
            "pronunciation_score": 0, "fluency_score": 0, "grammar_score": 0,
            "overall_comment": "AI feedback unavailable.",
            "pronunciation_items": [], "grammar_items": [],
            "filler_words": [], "improved_version": transcript,
            "improved_full": transcript,
            "transcript": transcript, "ollama_ok": False, "error": str(e),
        }

    feedback["prompt_title"] = prompt_title
    feedback["language"]     = data.get("language", "en")

    saved_session_id = None
    try:
        from db_helpers import save_session
        saved = save_session(feedback)
        saved_session_id = saved.id
        logger.info(f"Session saved to DB with id={saved_session_id}")
    except Exception as e:
        logger.warning(f"Could not save session: {e}")

    session_data = {k: v for k, v in feedback.items()}
    for field in ("improved_version", "improved_full"):
        if isinstance(session_data.get(field), str) and len(session_data[field]) > 500:
            session_data[field] = session_data[field][:500] + "..."
    session["last_feedback"] = session_data

    return jsonify({
        "status":              "ok",
        "session_id":          saved_session_id,
        "pronunciation_score": feedback.get("pronunciation_score", 0),
        "fluency_score":       feedback.get("fluency_score", 0),
        "grammar_score":       feedback.get("grammar_score", 0),
        "ollama_ok":           feedback.get("ollama_ok", False),
        "error":               feedback.get("error"),
    })


# ── API: Status ───────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    try:
        from ollama_feedback import check_ollama
        ollama_status = check_ollama()
    except Exception as e:
        ollama_status = {"ollama_running": False, "error": str(e)}

    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return jsonify({
        "whisper_model":      WHISPER_MODEL,
        "database_connected": db_ok,
        **ollama_status,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
