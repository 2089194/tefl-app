from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# ---------------------------------------------------------------------------
# Routes – one per screen, mirroring the wireframe structure
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Home screen – stats overview and quick actions."""
    # Placeholder stats; will be replaced with real DB queries
    stats = {
        "sessions_this_week": 12,
        "avg_score": 78,
        "streak": 5,
    }
    return render_template("home.html", stats=stats, active="home")


@app.route("/speak")
def speak():
    """Speaking task screen – prompt + recorder."""
    prompt = "Describe your favourite place to visit and explain why it is special to you."
    return render_template("speaking.html", prompt=prompt, active="speaking")


@app.route("/feedback")
def feedback():
    """Feedback screen – scores, annotated transcript, suggestions."""
    # Placeholder feedback data; will be replaced with real session results
    feedback_data = {
        "overall": 82,
        "pronunciation": 76,
        "fluency": 88,
        "confidence": 80,
        "transcript": [
            {"text": "My favourite place to visit is the ", "flag": None},
            {"text": "beach", "flag": "good"},
            {"text": " near my hometown. It is special because the ", "flag": None},
            {"text": "sunset", "flag": "needs_work"},
            {"text": " views are amazing and the sound of the waves is very ", "flag": None},
            {"text": "relaxing", "flag": "needs_work"},
            {"text": ".", "flag": None},
        ],
        "suggestions": [
            {
                "type": "tip",
                "title": "Stress the right syllables",
                "body": 'Try emphasising "SUNset" and "reLAXing" for clearer pronunciation.',
            },
            {
                "type": "good",
                "title": "Good pacing",
                "body": "Your speaking pace was well-controlled. Keep this up!",
            },
            {
                "type": "warning",
                "title": "Reduce filler words",
                "body": 'You used "um" 3 times. Try pausing silently instead.',
            },
        ],
    }
    return render_template("feedback.html", feedback=feedback_data, active="feedback")


@app.route("/profile")
def profile():
    """Profile & progress screen – stats, chart, session history."""
    past_sessions = [
        {"date": "Feb 18", "prompt": "Describe your favourite place...", "score": 82, "duration": "0:45"},
        {"date": "Feb 17", "prompt": "Talk about a recent challenge...", "score": 75, "duration": "1:02"},
        {"date": "Feb 16", "prompt": "Explain a hobby you enjoy...", "score": 79, "duration": "0:38"},
        {"date": "Feb 15", "prompt": "Describe your daily routine...", "score": 68, "duration": "0:55"},
        {"date": "Feb 14", "prompt": "Tell us about your hometown...", "score": 71, "duration": "0:41"},
    ]
    trend = [45, 52, 58, 55, 62, 68, 71, 75, 79, 82]
    profile_stats = {
        "total_sessions": 32,
        "improvement": "+14%",
        "avg_per_week": "24m",
        "member_since": "Jan 2026",
    }
    return render_template(
        "profile.html",
        past_sessions=past_sessions,
        trend=trend,
        profile_stats=profile_stats,
        active="profile",
    )


# ---------------------------------------------------------------------------
# API stubs – will be wired to Whisper + Ollama in later sprints
# ---------------------------------------------------------------------------

@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    """
    Stub: receives audio blob, returns transcript.
    Sprint 2: wire to Whisper STT.
    """
    # audio = request.files.get("audio")
    return jsonify({"transcript": "Placeholder transcript from Whisper.", "status": "ok"})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    """
    Stub: receives transcript, returns AI feedback JSON.
    Sprint 2: wire to Ollama feedback engine.
    """
    data = request.get_json(silent=True) or {}
    transcript = data.get("transcript", "")
    return jsonify({
        "overall": 82,
        "pronunciation": 76,
        "fluency": 88,
        "confidence": 80,
        "suggestions": [
            {"type": "tip", "title": "Stress the right syllables", "body": "..."},
        ],
        "status": "ok",
    })


if __name__ == "__main__":
    app.run(debug=True)
