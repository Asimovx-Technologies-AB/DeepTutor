"""
Student Profile & Persona Manager.

Maintains student goals, learning pace, prior knowledge level, and
pedagogical modality preferences (visual, analogies, history, examples, theory).
Persists to database user_memory and in-memory cache.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.core.database import engine
from app.tutoring.models import StudentProfile
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ProfileManager:
    """Manages student learning persona and modality preferences."""

    def __init__(self) -> None:
        self._cache: Dict[str, StudentProfile] = {}

    def get_profile(self, user_id: str) -> StudentProfile:
        """Retrieves or initializes a student profile."""
        if not user_id:
            user_id = "default-user"

        if user_id in self._cache:
            return self._cache[user_id]

        profile = self._load_from_db(user_id)
        if not profile:
            profile = StudentProfile(user_id=user_id)

        self._cache[user_id] = profile
        return profile

    def update_profile(
        self,
        user_id: str,
        goal_level: Optional[str] = None,
        learning_pace: Optional[str] = None,
        prior_knowledge: Optional[str] = None,
        preferences: Optional[Dict[str, float]] = None,
    ) -> StudentProfile:
        """Updates and persists student profile settings."""
        profile = self.get_profile(user_id)

        if goal_level:
            profile.goal_level = goal_level
        if learning_pace:
            profile.learning_pace = learning_pace
        if prior_knowledge:
            profile.prior_knowledge = prior_knowledge
        if preferences:
            profile.preferences.update(preferences)

        self._cache[user_id] = profile
        self._persist_to_db(profile)
        return profile

    def save_profile(self, profile: StudentProfile) -> None:
        """Saves profile to cache and database."""
        self._cache[profile.user_id] = profile
        self._persist_to_db(profile)


    # ── Database persistence ──────────────────────────────────────────────

    def _load_from_db(self, user_id: str) -> Optional[StudentProfile]:
        """Loads profile from user_memory table."""
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT memory_json FROM user_memory WHERE user_id = :uid"),
                    {"uid": user_id},
                ).mappings().fetchone()

                if row and row.get("memory_json"):
                    data = row["memory_json"]
                    if isinstance(data, str):
                        data = json.loads(data)

                    profile_data = data.get("student_profile", {})
                    if profile_data:
                        return StudentProfile(
                            user_id=user_id,
                            goal_level=profile_data.get("goal_level", "Undergraduate"),
                            learning_pace=profile_data.get("learning_pace", "standard"),
                            prior_knowledge=profile_data.get("prior_knowledge", "intermediate"),
                            preferences=profile_data.get(
                                "preferences",
                                {
                                    "visual": 0.8,
                                    "analogy": 0.9,
                                    "history": 0.6,
                                    "example": 0.9,
                                    "theory": 0.7,
                                },
                            ),
                        )
        except Exception as exc:
            logger.debug("[ProfileManager] Notice loading profile from DB: %s", exc)

        return None

    def _persist_to_db(self, profile: StudentProfile) -> None:
        """Persists updated profile to user_memory table."""
        try:
            with engine.begin() as conn:
                existing_row = conn.execute(
                    text("SELECT memory_json FROM user_memory WHERE user_id = :uid"),
                    {"uid": profile.user_id},
                ).mappings().fetchone()

                mem = {}
                if existing_row and existing_row.get("memory_json"):
                    mem = existing_row["memory_json"]
                    if isinstance(mem, str):
                        mem = json.loads(mem)

                mem["student_profile"] = {
                    "goal_level": profile.goal_level,
                    "learning_pace": profile.learning_pace,
                    "prior_knowledge": profile.prior_knowledge,
                    "preferences": profile.preferences,
                }

                conn.execute(
                    text("""
                        INSERT INTO user_memory (user_id, memory_json, updated_at)
                        VALUES (:uid, CAST(:mem AS jsonb), now())
                        ON CONFLICT (user_id) DO UPDATE SET
                            memory_json = EXCLUDED.memory_json,
                            updated_at = now();
                    """),
                    {"uid": profile.user_id, "mem": json.dumps(mem)},
                )
        except Exception as exc:
            logger.debug("[ProfileManager] Notice saving profile to DB: %s", exc)


profile_manager = ProfileManager()
student_profile_manager = profile_manager
StudentProfileManager = ProfileManager
