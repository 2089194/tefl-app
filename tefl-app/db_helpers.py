"""
db_helpers.py
─────────────
Helper functions for saving and retrieving session data.
Keeps database logic out of app.py routes.
"""

from datetime import datetime, timezone, timedelta
from models import db, User, Session, FeedbackItem, Progress
import logging

logger = logging.getLogger(__name__)

# Default user
DEFAULT_USER_ID = 1


def get_or_create_default_user():
    """
    Get or create the default user for single-user mode.
    Sprint 5: replace with proper authentication.
    """
    user = User.query.get(DEFAULT_USER_ID)
    if not user:
        user = User(id=DEFAULT_USER_ID, name="Learner", native_language="Korean",
                    english_level="Intermediate", consent_given=True)
        db.session.add(user)
        db.session.commit()
        logger.info("Created default user (id=1)")
    return user


def save_session(feedback: dict, user_id: int = DEFAULT_USER_ID) -> Session:
    """
    Save a completed session and its feedback items to the database.

    Args:
        feedback: dict from ollama_feedback.generate_feedback()
        user_id:  the user who completed the session

    Returns:
        The saved Session object
    """
    try:
        session = Session(
            user_id             = user_id,
            prompt_title        = feedback.get("prompt_title", "Free Practice"),
            transcript          = feedback.get("transcript", ""),
            pronunciation_score = feedback.get("pronunciation_score", 0),
            fluency_score       = feedback.get("fluency_score", 0),
            grammar_score       = feedback.get("grammar_score", 0),
            overall_comment     = feedback.get("overall_comment", ""),
            improved_version    = feedback.get("improved_version", ""),
            improved_full       = feedback.get("improved_full", ""),
            language_detected   = feedback.get("language", "en"),
        )
        db.session.add(session)
        db.session.flush()  # get session.id before adding items

        # Save pronunciation items
        for item in feedback.get("pronunciation_items", [])[:3]:
            db.session.add(FeedbackItem(
                session_id = session.id,
                category   = "pronunciation",
                word       = item.get("word", ""),
                issue      = item.get("issue", ""),
                correction = item.get("correction", ""),
                phonetic   = item.get("phonetic", ""),
            ))

        # Save grammar items
        for item in feedback.get("grammar_items", [])[:3]:
            db.session.add(FeedbackItem(
                session_id  = session.id,
                category    = "grammar",
                incorrect   = item.get("incorrect", ""),
                correct     = item.get("correct", ""),
                explanation = item.get("explanation", ""),
                example     = item.get("example", ""),
            ))

        # Save filler words as fluency items
        for word in feedback.get("filler_words", []):
            db.session.add(FeedbackItem(
                session_id = session.id,
                category   = "fluency",
                word       = word,
            ))

        db.session.commit()
        _update_progress(user_id, session)
        logger.info(f"Saved session {session.id} for user {user_id}")
        return session

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to save session: {e}")
        raise


def _update_progress(user_id: int, session: Session):
    """Update the weekly progress aggregate for this user."""
    try:
        # Get the Monday of the current week
        today = datetime.now(timezone.utc).date()
        week_start = today - timedelta(days=today.weekday())

        progress = Progress.query.filter_by(
            user_id=user_id, week_start=week_start
        ).first()

        if progress:
            # Recalculate averages including the new session
            n = progress.session_count
            progress.avg_pronunciation = (progress.avg_pronunciation * n + session.pronunciation_score) / (n + 1)
            progress.avg_fluency       = (progress.avg_fluency * n + session.fluency_score) / (n + 1)
            progress.avg_grammar       = (progress.avg_grammar * n + session.grammar_score) / (n + 1)
            progress.session_count     = n + 1
        else:
            progress = Progress(
                user_id           = user_id,
                week_start        = week_start,
                avg_pronunciation = session.pronunciation_score,
                avg_fluency       = session.fluency_score,
                avg_grammar       = session.grammar_score,
                session_count     = 1,
            )
            db.session.add(progress)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Progress update failed (non-fatal): {e}")


def get_recent_sessions(user_id: int = DEFAULT_USER_ID, limit: int = 20) -> list:
    """Get recent sessions for the history screen."""
    sessions = (
        Session.query
        .filter_by(user_id=user_id)
        .order_by(Session.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id":                   s.id,
            "prompt_title":         s.prompt_title,
            "date":                 s.date_display,
            "pronunciation_score":  s.pronunciation_score,
            "fluency_score":        s.fluency_score,
            "grammar_score":        s.grammar_score,
            "avg_score":            s.avg_score,
        }
        for s in sessions
    ]


def get_home_stats(user_id: int = DEFAULT_USER_ID) -> dict:
    """Get stats for the home screen stat tiles."""
    user = User.query.get(user_id)
    if not user:
        return {"sessions_this_week": 0, "avg_score": 0, "streak": 0}

    # Sessions this week
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    sessions_this_week = (
        Session.query
        .filter(Session.user_id == user_id, Session.created_at >= week_ago)
        .count()
    )

    return {
        "sessions_this_week": sessions_this_week,
        "avg_score":          user.avg_score(),
        "streak":             user.streak_days(),
    }


def get_session_by_id(session_id: int, user_id: int = DEFAULT_USER_ID):
    """Get a specific session for the feedback screen (e.g. from history)."""
    return Session.query.filter_by(id=session_id, user_id=user_id).first()
