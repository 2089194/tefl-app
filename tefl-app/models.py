"""
models.py
─────────
SQLAlchemy ORM models for the TEFL App feedback application.

Tables:
  users           – student accounts and settings
  sessions        – each speaking practice session
  feedback_items  – individual pronunciation / grammar / fluency items
  progress        – weekly aggregated scores (denormalised for fast queries)

Sprint 4: these models replace the PAST_SESSIONS placeholder in app.py.
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(120), nullable=False, default="Learner")
    email            = db.Column(db.String(255), unique=True, nullable=True)
    native_language  = db.Column(db.String(80),  nullable=True)
    english_level    = db.Column(db.String(20),  nullable=True, default="Intermediate")
    save_recordings  = db.Column(db.Boolean, default=False, nullable=False)
    consent_given    = db.Column(db.Boolean, default=False, nullable=False)
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    sessions = db.relationship("Session", back_populates="user",
                               cascade="all, delete-orphan", lazy="dynamic")

    def __repr__(self):
        return f"<User {self.id} {self.name}>"

    def avg_score(self):
        """Calculate average overall score across all sessions."""
        sessions = self.sessions.all()
        if not sessions:
            return 0
        total = sum(
            (s.pronunciation_score + s.fluency_score + s.grammar_score) / 3
            for s in sessions
        )
        return round(total / len(sessions))

    def streak_days(self):
        """Calculate current practice streak in days."""
        from sqlalchemy import func
        dates = (
            db.session.query(func.date(Session.created_at))
            .filter(Session.user_id == self.id)
            .distinct()
            .order_by(func.date(Session.created_at).desc())
            .all()
        )
        if not dates:
            return 0
        streak = 0
        today = datetime.now(timezone.utc).date()
        for i, (date,) in enumerate(dates):
            expected = today - __import__("datetime").timedelta(days=i)
            if date == expected:
                streak += 1
            else:
                break
        return streak


class Session(db.Model):
    __tablename__ = "sessions"

    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    prompt_title        = db.Column(db.String(255), nullable=False, default="Free Practice")
    transcript          = db.Column(db.Text,    nullable=True)
    pronunciation_score = db.Column(db.Integer, nullable=False, default=0)
    fluency_score       = db.Column(db.Integer, nullable=False, default=0)
    grammar_score       = db.Column(db.Integer, nullable=False, default=0)
    overall_comment     = db.Column(db.Text,    nullable=True)
    improved_version    = db.Column(db.Text,    nullable=True)
    improved_full       = db.Column(db.Text,    nullable=True)
    language_detected   = db.Column(db.String(10), nullable=True, default="en")
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    user           = db.relationship("User", back_populates="sessions")
    feedback_items = db.relationship("FeedbackItem", back_populates="session",
                                     cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Session {self.id} user={self.user_id} prompt='{self.prompt_title}'>"

    @property
    def avg_score(self):
        return round((self.pronunciation_score + self.fluency_score + self.grammar_score) / 3)

    @property
    def date_display(self):
        return self.created_at.strftime("%d %b %Y")

    @property
    def pronunciation_items(self):
        return [i for i in self.feedback_items if i.category == "pronunciation"]

    @property
    def grammar_items(self):
        return [i for i in self.feedback_items if i.category == "grammar"]

    @property
    def filler_words(self):
        items = [i for i in self.feedback_items if i.category == "fluency"]
        return [i.word for i in items if i.word]

    def to_feedback_dict(self):
        """Return a dict in the format expected by the feedback template."""
        return {
            "prompt_title":        self.prompt_title,
            "transcript":          self.transcript or "",
            "pronunciation":       self.pronunciation_score,
            "fluency":             self.fluency_score,
            "grammar":             self.grammar_score,
            "overall_comment":     self.overall_comment or "",
            "pronunciation_items": [i.to_dict() for i in self.pronunciation_items],
            "grammar_items":       [i.to_dict() for i in self.grammar_items],
            "filler_words":        self.filler_words,
            "improved_version":    self.improved_version or "",
            "improved_full":       self.improved_full or "",
            "ollama_ok":           True,
        }


class FeedbackItem(db.Model):
    __tablename__ = "feedback_items"

    id          = db.Column(db.Integer, primary_key=True)
    session_id  = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    category    = db.Column(db.String(20), nullable=False)   # pronunciation | grammar | fluency

    # Grammar fields
    incorrect   = db.Column(db.Text, nullable=True)
    correct     = db.Column(db.Text, nullable=True)
    explanation = db.Column(db.Text, nullable=True)
    example     = db.Column(db.Text, nullable=True)

    # Pronunciation fields
    word        = db.Column(db.String(100), nullable=True)
    issue       = db.Column(db.Text,        nullable=True)
    correction  = db.Column(db.String(200), nullable=True)
    phonetic    = db.Column(db.String(100), nullable=True)

    # Relationship
    session = db.relationship("Session", back_populates="feedback_items")

    def to_dict(self):
        if self.category == "pronunciation":
            return {
                "word":       self.word or "",
                "issue":      self.issue or "",
                "correction": self.correction or "",
                "phonetic":   self.phonetic or "",
            }
        elif self.category == "grammar":
            return {
                "incorrect":   self.incorrect or "",
                "correct":     self.correct or "",
                "explanation": self.explanation or "",
                "example":     self.example or "",
            }
        return {}


class Progress(db.Model):
    """
    Weekly aggregated progress — pre-computed for fast chart queries.
    Populated by save_session() after each session.
    """
    __tablename__ = "progress"

    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    week_start          = db.Column(db.Date,    nullable=False)
    avg_pronunciation   = db.Column(db.Float,   nullable=False, default=0)
    avg_fluency         = db.Column(db.Float,   nullable=False, default=0)
    avg_grammar         = db.Column(db.Float,   nullable=False, default=0)
    session_count       = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("user_id", "week_start", name="uq_user_week"),
    )

    def __repr__(self):
        return f"<Progress user={self.user_id} week={self.week_start}>"
