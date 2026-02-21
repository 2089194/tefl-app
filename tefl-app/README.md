# tefl-app – Flask Application

AI-powered spoken English feedback tool for TEFL learners.

## Project Structure

```
tefl-app/
├── app.py                  # Flask routes & API stubs
├── requirements.txt
├── templates/
│   ├── base.html           # Shell: top bar + bottom nav
│   ├── home.html           # Home screen
│   ├── speaking.html       # Speaking task + recorder
│   ├── feedback.html       # Feedback & scores
│   └── profile.html        # Profile & progress
└── static/
    ├── css/main.css        # All styles (design token system)
    └── js/
        ├── main.js         # Shared UI utilities
        └── recorder.js     # MediaRecorder + waveform + API calls
```

## Sprint 1 – Framework (current)
- Flask route scaffold for all 4 screens
- Jinja2 templates porting the wireframe UI
- CSS design-token system mirroring the wireframe's greyscale/dashed aesthetic
- MediaRecorder integration (mic access, waveform, timer, state machine)
- API stub endpoints: `/api/transcribe` and `/api/feedback`

## Sprint 2 – Core Engine (next)
- Wire `/api/transcribe` → OpenAI Whisper STT
- Wire `/api/feedback` → Ollama LLM feedback engine
- PostgreSQL models (users, sessions, feedback, progress)
- User auth (Flask-Login)

## Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run development server
python app.py
# → http://127.0.0.1:5000
```

## API Stubs

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/transcribe` | POST | Receives `audio` file; returns transcript JSON |
| `/api/feedback` | POST | Receives `transcript` JSON; returns scores + suggestions |

Both return placeholder data in Sprint 1.
