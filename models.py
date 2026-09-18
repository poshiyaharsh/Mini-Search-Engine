"""
Mini Search Engine - Database Models
====================================
Defines the User and SavedSearch models backed by SQLite via Flask-SQLAlchemy.
Passwords are securely hashed with Werkzeug (never stored in plaintext).
"""

from datetime import datetime, timezone
import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User account model for session management and personal saved searches."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    saved_searches = db.relationship(
        "SavedSearch",
        backref="user",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(SavedSearch.created_at)",
    )

    def set_password(self, password: str):
        """Hashes the password using scrypt/pbkdf2."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verifies the password against the stored hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


class SavedSearch(db.Model):
    """Saved query history model strictly isolated per user."""
    __tablename__ = "saved_searches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    query_text = db.Column(db.String(500), nullable=False)
    algo = db.Column(db.String(20), default="bm25", nullable=False)
    filters_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def get_filters(self) -> dict:
        """Parses stored filters JSON or returns defaults."""
        if not self.filters_json:
            return {"source": "all", "min_score": 0.0}
        try:
            return json.loads(self.filters_json)
        except Exception:
            return {"source": "all", "min_score": 0.0}

    def to_dict(self) -> dict:
        """Serializes saved search to dict for API JSON responses."""
        return {
            "id": self.id,
            "query": self.query_text,
            "algo": self.algo,
            "filters": self.get_filters(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<SavedSearch id={self.id} user_id={self.user_id} query={self.query_text[:30]}>"
