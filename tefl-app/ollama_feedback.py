"""
ollama_feedback.py
──────────────────
AI feedback engine using Ollama (local LLM, free, zero-cost).

Ollama must be installed and running separately:
  1. Download from https://ollama.com
  2. Install and run: ollama serve
  3. Pull a model: ollama pull llama3.2
     (or mistral, phi3, gemma2 — see README for recommendations)

This module sends the student's transcript to the LLM with a carefully
designed prompt and parses the structured JSON response.

Prompt design follows pedagogical principles from the literature review:
  - Selective feedback (max 3 items per category — avoid overwhelming)
  - Non-judgemental, encouraging tone (Krashen's affective filter)
  - Concrete corrections with examples (not just flagging errors)
  - Contextualised to non-native English speakers
"""

import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llama3.2")


# ── Prompt ────────────────────────────────────────────────────
FEEDBACK_PROMPT = """You are a supportive English language teacher giving feedback to a non-native English speaker. Your tone is encouraging, specific, and non-judgmental.

Analyse the following spoken English transcript and return ONLY a valid JSON object with no other text, markdown, or explanation.

TRANSCRIPT:
{transcript}

Return this exact JSON structure:
{{
  "pronunciation_score": <integer 0-100>,
  "fluency_score": <integer 0-100>,
  "grammar_score": <integer 0-100>,
  "overall_comment": "<one encouraging sentence summarising overall performance>",
  "pronunciation_items": [
    {{
      "word": "<the mispronounced word>",
      "issue": "<brief description of the issue>",
      "correction": "<syllable breakdown e.g. COM-pu-ter>",
      "phonetic": "<IPA notation e.g. /kəmˈpjuːtər/>"
    }}
  ],
  "grammar_items": [
    {{
      "incorrect": "<the incorrect phrase as spoken>",
      "correct": "<the corrected version>",
      "explanation": "<brief, friendly explanation of the rule>",
      "example": "<a new example sentence using the correct form>"
    }}
  ],
  "filler_words": ["<list>", "<of>", "<filler words detected>"],
  "improved_version": "<the student's exact message rewritten with only fluency improvements — same content, better flow>",
  "improved_full": "<a complete, polished version of what the student said, correcting all errors while preserving their intended meaning>"
}}

Rules:
- pronunciation_items: maximum 3 items, prioritise the most important issues
- grammar_items: maximum 3 items, prioritise the most important errors
- If there are no pronunciation/grammar issues, return empty arrays []
- filler_words: only include words actually present in the transcript (um, uh, like, you know, etc.)
- Scores should reflect genuine assessment: 60-75 for many errors, 75-85 for some errors, 85-95 for minor errors, 95-100 for near-perfect
- Be encouraging but honest — do not inflate scores
- Return ONLY the JSON object, no other text"""


def generate_feedback(transcript: str) -> dict:
    """
    Send transcript to Ollama and return structured feedback.

    Args:
        transcript: The student's spoken English text from Whisper

    Returns:
        dict with feedback data, or error dict if Ollama unavailable
    """
    if not transcript or not transcript.strip():
        return _empty_feedback("No transcript provided.")

    prompt = FEEDBACK_PROMPT.format(transcript=transcript.strip())

    payload = json.dumps({
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,   # Low temp for consistent structured output
            "num_predict": 1000,  # Enough tokens for the full JSON response
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            response_text = data.get("response", "").strip()

        logger.info(f"Ollama raw response (first 200 chars): {response_text[:200]}")
        return _parse_response(response_text, transcript)

    except urllib.error.URLError as e:
        logger.error(f"Ollama connection error: {e}")
        return _error_feedback(
            "Ollama is not running. Please start it with: ollama serve",
            transcript
        )
    except Exception as e:
        logger.error(f"Ollama feedback error: {e}")
        return _error_feedback(str(e), transcript)


def _parse_response(response_text: str, transcript: str) -> dict:
    """Parse Ollama's response, extracting JSON even if wrapped in markdown."""
    # Strip markdown code fences if present
    text = response_text.strip()
    if "```" in text:
        # Extract content between first ``` and last ```
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    # Find JSON object boundaries
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        logger.error("No JSON object found in Ollama response")
        return _error_feedback("Could not parse AI response as JSON.", transcript)

    json_str = text[start:end]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nText was: {json_str[:300]}")
        return _error_feedback("AI response was not valid JSON.", transcript)

    # Validate and clamp scores
    for score_key in ("pronunciation_score", "fluency_score", "grammar_score"):
        val = parsed.get(score_key, 70)
        parsed[score_key] = max(0, min(100, int(val)))

    # Ensure required keys exist with safe defaults
    parsed.setdefault("pronunciation_items", [])
    parsed.setdefault("grammar_items", [])
    parsed.setdefault("filler_words", [])
    parsed.setdefault("improved_version", transcript)
    parsed.setdefault("improved_full", transcript)
    parsed.setdefault("overall_comment", "Good effort! Keep practising.")

    # Cap items at 3 (model sometimes ignores this instruction)
    parsed["pronunciation_items"] = parsed["pronunciation_items"][:3]
    parsed["grammar_items"]       = parsed["grammar_items"][:3]

    parsed["transcript"]  = transcript
    parsed["ollama_ok"]   = True
    parsed["error"]       = None

    logger.info(
        f"Feedback parsed OK — "
        f"pronunciation={parsed['pronunciation_score']} "
        f"fluency={parsed['fluency_score']} "
        f"grammar={parsed['grammar_score']}"
    )
    return parsed


def _empty_feedback(reason: str) -> dict:
    return {
        "pronunciation_score": 0, "fluency_score": 0, "grammar_score": 0,
        "overall_comment": reason,
        "pronunciation_items": [], "grammar_items": [],
        "filler_words": [], "improved_version": "", "improved_full": "",
        "transcript": "", "ollama_ok": False, "error": reason,
    }


def _error_feedback(reason: str, transcript: str) -> dict:
    """Return a graceful fallback when Ollama is unavailable."""
    return {
        "pronunciation_score": 0, "fluency_score": 0, "grammar_score": 0,
        "overall_comment": "AI feedback is currently unavailable.",
        "pronunciation_items": [], "grammar_items": [],
        "filler_words": [], "improved_version": transcript,
        "improved_full": transcript,
        "transcript": transcript,
        "ollama_ok": False,
        "error": reason,
    }


def check_ollama() -> dict:
    """Check if Ollama is running and the configured model is available."""
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/tags",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
            model_ready = any(OLLAMA_MODEL in m for m in models)
            return {
                "ollama_running": True,
                "model_configured": OLLAMA_MODEL,
                "model_available": model_ready,
                "available_models": models,
                "pull_command": f"ollama pull {OLLAMA_MODEL}" if not model_ready else None,
            }
    except urllib.error.URLError:
        return {
            "ollama_running": False,
            "model_configured": OLLAMA_MODEL,
            "model_available": False,
            "available_models": [],
            "start_command": "ollama serve",
        }
    except Exception as e:
        return {
            "ollama_running": False,
            "error": str(e),
        }
