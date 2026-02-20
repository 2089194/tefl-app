from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# ── Shared data ──────────────────────────────────────────────
PROMPTS = [
    {"title": "Describe your weekend",       "description": "Talk about what you did last weekend"},
    {"title": "Talk about your studies",     "description": "Share about your academic interests"},
    {"title": "Describe a recent challenge", "description": "Explain a difficulty you overcame"},
]

PLACEHOLDER_FEEDBACK = {
    "prompt_title":    "Describe your weekend",
    "transcript":      "Last weekend I go to the park with my friend. We have very good time. The weather was beautiful and we take many photos.",
    "pronunciation":   76,
    "fluency":         80,
    "grammar":         68,
    "pronunciation_items": [
        {"word": "beautiful",    "issue": "Stress on wrong syllable", "correction": "BEAU-ti-ful",     "phonetic": "/ˈbjuːtɪfəl/"},
        {"word": "comfortable",  "issue": "Missing syllable",          "correction": "COM-for-ta-ble",  "phonetic": "/ˈkʌmfətəbəl/"},
    ],
    "grammar_items": [
        {"incorrect": "I go to the park",     "correct": "I went to the park",       "explanation": "Use past tense when describing past events.",               "example": "Yesterday, I walked to school."},
        {"incorrect": "We have very good time","correct": "We had a very good time",  "explanation": 'Past tense verb and article "a" are needed.',              "example": "They had a great party."},
    ],
    "filler_words":    ["um", "like"],
    "improved_version":"Last weekend, I went to the park with my friend. We had a wonderful time.",
    "improved_full":   "Last weekend, I went to the park with my friend. We had a very good time.\nThe weather was beautiful, and we took many photos.\nIt was a perfect way to spend a relaxing afternoon.",
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

# ── Main app screens ──────────────────────────────────────────
@app.route("/")
def index():
    stats = {
        "sessions_this_week": len(PAST_SESSIONS),
        "avg_score": int(sum((s["pronunciation_score"]+s["fluency_score"]+s["grammar_score"])/3 for s in PAST_SESSIONS) / len(PAST_SESSIONS)) if PAST_SESSIONS else 0,
        "streak": min(len(PAST_SESSIONS), 7),
    }
    return render_template("home.html", stats=stats, prompts=PROMPTS, user_name="Learner", show_nav=True, active="home")

@app.route("/speak")
def speak():
    prompt_title = request.args.get("prompt", "Free Practice")
    return render_template("speaking.html", prompt_title=prompt_title, show_nav=True, active="speaking")

@app.route("/feedback")
def feedback():
    return render_template("feedback.html", feedback=PLACEHOLDER_FEEDBACK, show_nav=True, active="feedback")

@app.route("/history")
def history():
    return render_template("history.html", past_sessions=PAST_SESSIONS, show_nav=True, active="history")

@app.route("/profile")
def profile():
    return render_template("profile.html",
        user_name="Learner", user_email="", native_language="Korean",
        english_level="Intermediate", show_nav=True, active="profile")

# ── API stubs (Sprint 2: wire to Whisper + Ollama) ───────────
@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    return jsonify({"transcript": "Placeholder transcript — Whisper STT coming in Sprint 2.", "status": "ok"})

@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    return jsonify({
        "pronunciation": 76, "fluency": 80, "grammar": 68,
        "filler_words": ["um", "like"],
        "improved_version": "Placeholder improved version.",
        "status": "ok"
    })

if __name__ == "__main__":
    app.run(debug=True)
