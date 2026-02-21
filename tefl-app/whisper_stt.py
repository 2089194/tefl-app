"""
whisper_stt.py
──────────────
Speech-to-text module using OpenAI Whisper (local, free).

Model sizes (change WHISPER_MODEL in .env to switch):
  tiny   – fastest, least accurate  (~75MB,  CPU fine)
  base   – good balance             (~145MB, CPU fine)
  small  – better accuracy          (~465MB, CPU acceptable)
  medium – high accuracy            (~1.5GB, GPU recommended)
  large  – best accuracy            (~3GB,   GPU recommended)

"""

import os
import tempfile
import logging

logger = logging.getLogger(__name__)

# Model cache – loaded once, reused across requests
_model = None
_model_name = None


def _get_model(model_name: str = "base"):
    """Load and cache the Whisper model."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        try:
            import whisper
            logger.info(f"Loading Whisper model: {model_name} (first request only)")
            _model = whisper.load_model(model_name)
            _model_name = model_name
            logger.info("Whisper model loaded successfully.")
        except ImportError:
            raise RuntimeError(
                "openai-whisper is not installed. "
                "Run: pip install openai-whisper"
            )
    return _model


def transcribe_audio(audio_bytes: bytes, model_name: str = "small") -> dict:
    """
    Transcribe audio bytes using Whisper.

    Args:
        audio_bytes: Raw audio data (webm, mp3, wav, m4a, etc.)
        model_name:  Whisper model size (tiny/base/small/medium/large)

    Returns:
        dict with keys:
            transcript (str)      – full transcription text
            language   (str)      – detected language code e.g. 'en'
            segments   (list)     – list of timed segment dicts
            error      (str|None) – error message if transcription failed
    """
    # Write audio bytes to a temp file (Whisper needs a file path)
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = _get_model(model_name)

        # fp16=False ensures CPU compatibility
        result = model.transcribe(
            tmp_path,
            language=None,      # auto-detect language
            task="transcribe",  # keep original language (not translate)
            fp16=False,         # safe for CPU
            verbose=False,
        )

        return {
            "transcript": result.get("text", "").strip(),
            "language":   result.get("language", "unknown"),
            "segments":   result.get("segments", []),
            "error":      None,
        }

    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        return {
            "transcript": "",
            "language":   "unknown",
            "segments":   [],
            "error":      str(e),
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def get_model_name() -> str:
    """Return configured model name from .env or default 'base'."""
    return os.environ.get("WHISPER_MODEL", "base")
