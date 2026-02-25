"""
whisper_stt.py
──────────────
Speech-to-text using OpenAI Whisper via the Hugging Face transformers library.

Model: openai/whisper-large-v3-turbo
  - Distilled from whisper-large-v3
  - Near large-v3 accuracy at significantly faster speed
  - Best filler word and disfluency preservation of all Whisper variants
  - Runs on GPU (CUDA) if available (~1.6GB VRAM), otherwise CPU (~3GB RAM)
  - Downloaded once (~1.6GB) and cached to disk

Fallback: if transformers model fails, falls back to openai-whisper base model.

Key flags used:
  condition_on_previous_text=False  — prevents Whisper from correcting
      subsequent words based on prior output, preserving disfluencies
  return_timestamps=True            — required for audio longer than 30 seconds
"""

import os
import tempfile
import logging

logger = logging.getLogger(__name__)

# ── Model cache ───────────────────────────────────────────────
_pipeline = None
_fallback_model = None
_loaded_model_name = None

HUGGINGFACE_MODEL = "openai/whisper-large-v3-turbo"


def _get_pipeline():
    """Load and cache the Hugging Face whisper pipeline."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    try:
        import torch
        from transformers import pipeline

        logger.info(f"Loading {HUGGINGFACE_MODEL} via transformers (first request only)")
        logger.info("This may take a few minutes on first run — model is ~1.6GB")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype  = torch.float16 if device == "cuda" else torch.float32

        _pipeline = pipeline(
            "automatic-speech-recognition",
            model=HUGGINGFACE_MODEL,
            device=device,
            dtype=dtype,
        )
        logger.info(f"Loaded {HUGGINGFACE_MODEL} successfully on {device}")
        return _pipeline

    except ImportError as e:
        logger.error(f"transformers/torch not installed: {e}")
        raise RuntimeError(
            "transformers and torch are required for whisper-large-v3-turbo. "
            "Run: pip install transformers torch"
        )
    except Exception as e:
        logger.error(f"Failed to load {HUGGINGFACE_MODEL}: {e}")
        raise


def _get_fallback_model(model_name: str = "small"):
    """Load standard openai-whisper as fallback."""
    global _fallback_model, _loaded_model_name
    if _fallback_model is None or _loaded_model_name != model_name:
        try:
            import whisper
            logger.info(f"Loading fallback Whisper model: {model_name}")
            _fallback_model = whisper.load_model(model_name)
            _loaded_model_name = model_name
            logger.info("Fallback Whisper model loaded.")
        except ImportError:
            raise RuntimeError("openai-whisper not installed. Run: pip install openai-whisper")
    return _fallback_model


def transcribe_audio(audio_bytes: bytes, model_name: str = "large-v3-turbo") -> dict:
    """
    Transcribe audio bytes using whisper-large-v3-turbo via transformers.
    Falls back to openai-whisper small if transformers is unavailable.
    """
    suffix = ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        # Try transformers pipeline first
        try:
            pipe = _get_pipeline()
            result = _transcribe_with_pipeline(pipe, tmp_path)
            logger.info(f"Transcribed with {HUGGINGFACE_MODEL}: {len(result['transcript'])} chars")
            return result

        except RuntimeError as e:
            # transformers not available — fall back to openai-whisper
            logger.warning(f"Falling back to openai-whisper: {e}")
            fallback_name = model_name if model_name in ("tiny", "base", "small", "medium") else "small"
            return _transcribe_with_whisper(tmp_path, fallback_name)

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return {"transcript": "", "language": "unknown", "segments": [], "error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _transcribe_with_pipeline(pipe, audio_path: str) -> dict:
    """Transcribe using the Hugging Face transformers pipeline."""
    result = pipe(
        audio_path,
        generate_kwargs={
            "language":                 "english",
            "condition_on_prev_tokens": False,  # preserve disfluencies
        },
        return_timestamps=True,
    )
    transcript = result.get("text", "").strip()
    return {
        "transcript": transcript,
        "language":   "en",
        "segments":   [],
        "error":      None,
    }


def _transcribe_with_whisper(audio_path: str, model_name: str) -> dict:
    """Transcribe using standard openai-whisper package."""
    import whisper
    model = _get_fallback_model(model_name)
    result = model.transcribe(
        audio_path,
        language=None,
        task="transcribe",
        fp16=False,
        verbose=False,
        condition_on_previous_text=False,
        no_speech_threshold=0.3,
        temperature=0.0,
    )
    return {
        "transcript": result.get("text", "").strip(),
        "language":   result.get("language", "unknown"),
        "segments":   result.get("segments", []),
        "error":      None,
    }


def get_model_name() -> str:
    """Return the configured model name from env or default."""
    return os.environ.get("WHISPER_MODEL", "large-v3-turbo")