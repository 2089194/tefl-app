"""
whisper_stt.py
──────────────
Speech-to-text using faster_CrisperWhisper via the faster-whisper framework.

Model: nyrahealth/faster_CrisperWhisper
  - CrisperWhisper converted to CTranslate2 (INT8 quantised)
  - Verbatim transcription: preserves um, uh, like, false starts, stutters
  - ~1.5–2 GB RAM on CPU with INT8 (vs ~3.7 GB for whisper-large via PyTorch)
  - No ffmpeg system install required (PyAV handles audio decoding)
  - Downloaded once (~1.5 GB) and cached to ~/.cache/huggingface/hub/

Key difference from standard Whisper:
  CrisperWhisper was fine-tuned specifically to NOT normalise disfluencies.
  No inference-time flags or prompts are needed — it captures filler words
  by default.

Sprint 6 fixes:
  - vad_filter disabled (was removing genuine speech)
  - beam_size reduced to 1 (reduces word-joining artefacts)
  - _clean_transcript() normalises CrisperWhisper output artefacts
"""

import os
import re
import tempfile
import logging

logger = logging.getLogger(__name__)

_model = None
MODEL_ID = "Systran/faster-whisper-small"


def _get_model():
    """Load and cache the faster_CrisperWhisper model."""
    global _model
    if _model is not None:
        return _model

    try:
        from faster_whisper import WhisperModel

        logger.info(f"Loading {MODEL_ID} (first request only — ~1.5 GB download)")
        logger.info("Using INT8 quantisation on CPU — lower memory, faster inference")

        _model = WhisperModel(
            MODEL_ID,
            device="cpu",
            compute_type="int8",   # quantised: ~1.5–2 GB RAM vs ~3.7 GB float32
            cpu_threads=6,         # adjust to match your core count
            download_root=None,    # uses default HF cache (~/.cache/huggingface)
        )

        logger.info(f"Loaded {MODEL_ID} successfully")
        return _model

    except ImportError:
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        )
    except Exception as e:
        logger.error(f"Failed to load {MODEL_ID}: {e}")
        raise


def _clean_transcript(text: str) -> str:
    """
    Normalise CrisperWhisper output artefacts to flowing plain text.

    CrisperWhisper (via CTranslate2) can produce:
      - "Word.Next.Word"     -- periods used as word separators
      - "Word,Next,Word"     -- commas used as word separators
      - "[UH]", "[UM]"       -- disfluencies wrapped in square brackets
      - "Lastweekend"        -- missing space at word boundaries (camelCase join)
      - Excess whitespace

    This function converts all of the above to clean, readable text
    while preserving the disfluency words themselves (uh, um, er, etc.)
    which are the primary signals for fluency scoring.
    """
    # "Word.Next" or "Word,Next" -> "Word Next"
    # Only fires when punctuation sits directly between word characters,
    # so genuine sentence-ending punctuation (followed by space) is unaffected
    text = re.sub(r'(?<=[A-Za-z])[.,](?=[A-Za-z\[])', ' ', text)

    # "[UH]" / "[UM]" / "[ER]" / "[HM]" -> "uh" / "um" / "er" / "hm"
    text = re.sub(r'\[([A-Za-z]+)\]', lambda m: m.group(1).lower(), text)

    # "Lastweekend" / "Iwentto" -> insert space before capital after lowercase
    # Handles camelCase-style joins at segment boundaries
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)

    # Collapse multiple spaces to single space
    text = re.sub(r'  +', ' ', text)

    return text.strip()


def transcribe_audio(audio_bytes: bytes, model_name: str = None) -> dict:
    """
    Transcribe audio bytes using faster_CrisperWhisper.

    Args:
        audio_bytes: Raw audio data (webm, mp3, wav, etc.)
        model_name:  Ignored -- model is fixed to CrisperWhisper.
                     Kept for API compatibility with previous whisper_stt.py.

    Returns:
        dict with keys:
            transcript (str)      -- full verbatim transcription
            language   (str)      -- detected language code e.g. 'en'
            segments   (list)     -- list of segment dicts with timestamps
            error      (str|None) -- error message if transcription failed
    """
    # Write audio bytes to a temp file -- faster-whisper expects a file path
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = _get_model()

        segments_generator, info = model.transcribe(
            tmp_path,
            language="en",
            beam_size=1,       # greedy decoding -- faster and reduces word-joining
                               # artefacts observed with beam_size=5 on conversational speech
            vad_filter=False,  # disabled -- default VAD was too aggressive and
                               # removed genuine speech, causing truncated transcripts
        )

        # Consume the generator -- must be done before the temp file is deleted
        segments = []
        transcript_parts = []
        for seg in segments_generator:
            segments.append({
                "start": seg.start,
                "end":   seg.end,
                "text":  seg.text.strip(),
            })
            transcript_parts.append(seg.text)

        raw_transcript = " ".join(transcript_parts).strip()
        transcript = _clean_transcript(raw_transcript)

        logger.info(
            f"Transcribed {len(audio_bytes)//1024}KB -- "
            f"{len(transcript)} chars, language={info.language} "
            f"({info.language_probability:.0%} confidence)"
        )

        if raw_transcript != transcript:
            logger.debug(
                f"Cleaned transcript: {raw_transcript!r} -> {transcript!r}"
            )

        return {
            "transcript": transcript,
            "language":   info.language,
            "segments":   segments,
            "error":      None,
        }

    except Exception as e:
        logger.error(f"Transcription error: {e}")
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
    """Return model identifier -- kept for API compatibility."""
    return MODEL_ID
