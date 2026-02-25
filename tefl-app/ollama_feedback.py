"""
ollama_feedback.py
──────────────────
AI feedback engine using Ollama (local LLM, free, zero-cost).
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
# Note: phonetic field uses plain text (e.g. "kuhm-PYOO-ter") not IPA slashes
# IPA notation was causing JSON truncation due to special characters
FEEDBACK_PROMPT = """You are an English teacher giving feedback to a non-native speaker. Return ONLY valid JSON.

TRANSCRIPT: {transcript}

Analyse the transcript and return this JSON with real values filled in:
{{"pronunciation_score":75,"fluency_score":80,"grammar_score":70,"overall_comment":"Great effort, keep practising your English!","pronunciation_items":[{{"word":"actual mispronounced word from transcript","issue":"describe the actual problem","correction":"HOW-to-say-it","phonetic":"how-it-sounds"}}],"grammar_items":[{{"incorrect":"actual wrong phrase from transcript","correct":"corrected version","explanation":"why it is wrong in plain English","example":"new sentence using correct form"}}],"improved_version":"rewrite transcript improving flow and removing repetition","improved_full":"rewrite transcript fixing all grammar and pronunciation errors"}}

Rules:
- Fill every field with real analysis of the transcript above — do not leave fields empty
- pronunciation_items: up to 2 real mispronounced words from the transcript, or [] if none
- grammar_items: up to 2 real grammar errors from the transcript, or [] if none
- improved_version: rewrite the EXACT words from the transcript above with only flow improvements
- improved_full: rewrite the EXACT words from the transcript above fixing all errors — stay close to what was said
- Scores: 60-75 many errors, 75-85 some errors, 85-95 minor errors, 95-100 perfect
- Return ONLY the JSON, no other text"""

def generate_feedback(transcript: str) -> dict:
    """
    Send transcript to Ollama and return structured feedback.
    """
    if not transcript or not transcript.strip():
        return _empty_feedback("No transcript provided.")

    prompt = FEEDBACK_PROMPT.format(transcript=transcript.strip())

    payload = json.dumps({
        "model":  OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 600,  # Reduced for faster CPU inference
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:  # 5 min timeout for CPU inference
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
    text = response_text.strip()

    # Strip markdown code fences if present
    if "```" in text:
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
        # Try to salvage scores from partial response
        return _salvage_partial(json_str, transcript, str(e))

    # Validate and clamp scores
    for key in ("pronunciation_score", "fluency_score", "grammar_score"):
        val = parsed.get(key, 70)
        try:
            parsed[key] = max(0, min(100, int(val)))
        except (TypeError, ValueError):
            parsed[key] = 70

    # Safe defaults for all required keys
    parsed.setdefault("pronunciation_items", [])
    parsed.setdefault("grammar_items", [])
    parsed.setdefault("improved_version", transcript)
    parsed.setdefault("improved_full", transcript)
    parsed.setdefault("overall_comment", "Good effort! Keep practising.")

    # Always detect filler words in Python — never trust Ollama for this.
    # Ollama hallucinates filler words regardless of the prompt instruction.
    # Whisper also tends to clean up filler words so this is approximate,
    # but it is deterministic and never invents words that weren't spoken.
    parsed["filler_words"] = _detect_filler_words(transcript)

    # Cap items at 2
    parsed["pronunciation_items"] = parsed["pronunciation_items"][:2]
    parsed["grammar_items"]       = parsed["grammar_items"][:2]

    parsed["transcript"] = transcript
    parsed["ollama_ok"]  = True
    parsed["error"]      = None

    logger.info(
        f"Feedback parsed OK — "
        f"pronunciation={parsed['pronunciation_score']} "
        f"fluency={parsed['fluency_score']} "
        f"grammar={parsed['grammar_score']} "
        f"comment='{parsed.get('overall_comment','MISSING')}'"
    )
    return parsed


def _detect_filler_words(transcript: str) -> list:
    """
    Detect filler words directly from the transcript text.
    This is deterministic — it only returns words actually present in the text.
    Whisper often omits filler words during transcription, so absence here
    does not necessarily mean the student spoke fluently.
    """
    import re
    FILLERS = [
        "um", "umm", "uh", "uhh", "uhm",
        "like", "you know", "basically", "literally",
        "actually", "honestly", "right", "okay so",
        "i mean", "kind of", "sort of",
    ]
    text = transcript.lower()
    found = []
    for filler in FILLERS:
        # Use word boundaries to avoid matching substrings (e.g. "like" in "likely")
        pattern = r'\b' + re.escape(filler) + r'\b'
        if re.search(pattern, text):
            if filler not in found:
                found.append(filler.strip())
    return found


def _salvage_partial(json_str: str, transcript: str, parse_error: str) -> dict:
    """
    Try to extract scores from a truncated JSON response.
    The scores usually appear early in the response before truncation.
    """
    import re
    result = _error_feedback(f"Partial response: {parse_error}", transcript)

    patterns = {
        "pronunciation_score": r'"pronunciation_score"\s*:\s*(\d+)',
        "fluency_score":       r'"fluency_score"\s*:\s*(\d+)',
        "grammar_score":       r'"grammar_score"\s*:\s*(\d+)',
        "overall_comment":     r'"overall_comment"\s*:\s*"([^"]+)"',
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, json_str)
        if m:
            val = m.group(1)
            result[key] = max(0, min(100, int(val))) if key.endswith("_score") else val

    if any(result.get(k, 0) > 0 for k in ("pronunciation_score", "fluency_score", "grammar_score")):
        result["ollama_ok"] = True
        result["error"] = None
        logger.info(f"Salvaged partial response — scores extracted successfully")

    return result


def _empty_feedback(reason: str) -> dict:
    return {
        "pronunciation_score": 0, "fluency_score": 0, "grammar_score": 0,
        "overall_comment": reason,
        "pronunciation_items": [], "grammar_items": [],
        "filler_words": [], "improved_version": "", "improved_full": "",
        "transcript": "", "ollama_ok": False, "error": reason,
    }


def _error_feedback(reason: str, transcript: str) -> dict:
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
                "ollama_running":    True,
                "model_configured":  OLLAMA_MODEL,
                "model_available":   model_ready,
                "available_models":  models,
                "pull_command":      f"ollama pull {OLLAMA_MODEL}" if not model_ready else None,
            }
    except urllib.error.URLError:
        return {
            "ollama_running":   False,
            "model_configured": OLLAMA_MODEL,
            "model_available":  False,
            "available_models": [],
            "start_command":    "ollama serve",
        }
    except Exception as e:
        return {"ollama_running": False, "error": str(e)}