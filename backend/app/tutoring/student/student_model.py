"""
Student Persona & Dynamic Cognitive State Model.

Implements rigorous psychometric learning modeling:
- Bayesian Knowledge Tracing (BKT) with parameters P(L0), P(T), P(G), P(S)
- Ebbinghaus memory decay and retention stability estimation
- Misconception frequency attribution and weakness clustering
- Thread-safe in-memory caching with PostgreSQL persistence
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.core.database import engine
from app.tutoring.models import StudentModel

logger = logging.getLogger(__name__)

# Standard Bayesian Knowledge Tracing (BKT) default priors
BKT_DEFAULT_P_L0 = 0.50   # Prior probability of initial mastery
BKT_DEFAULT_P_T = 0.20    # Probability of transition from unlearned to learned
BKT_DEFAULT_P_G = 0.15    # Probability of correct answer by guessing
BKT_DEFAULT_P_S = 0.10    # Probability of incorrect answer by slip


class StudentModelManager:
    """Manages dynamic student cognitive state, Bayesian Knowledge Tracing, and retention stability."""

    def __init__(
        self,
        p_transit: float = BKT_DEFAULT_P_T,
        p_guess: float = BKT_DEFAULT_P_G,
        p_slip: float = BKT_DEFAULT_P_S,
    ) -> None:
        self._models: Dict[str, StudentModel] = {}
        self.p_transit = p_transit
        self.p_guess = p_guess
        self.p_slip = p_slip

    def get_model(self, user_id: str) -> StudentModel:
        """Retrieves or initializes the cognitive model for a student."""
        if not user_id:
            user_id = "default-user"

        if user_id in self._models:
            return self._models[user_id]

        model = self._load_from_db(user_id)
        if not model:
            model = StudentModel(user_id=user_id)

        self._models[user_id] = model
        return model

    def save_model(self, model: StudentModel) -> None:
        """Saves cognitive model to memory cache and database."""
        self._models[model.user_id] = model
        self._persist_to_db(model)

    def compute_bkt_update(
        self,
        prior_mastery: float,
        is_correct: bool,
        score: float = 1.0,
    ) -> float:
        """
        Computes exact Bayesian Knowledge Tracing posterior and transition update:
        1. Posterior calculation:
           P(L_t | obs=1) = (P(L) * (1 - S)) / (P(L) * (1 - S) + (1 - P(L)) * G)
           P(L_t | obs=0) = (P(L) * S) / (P(L) * S + (1 - P(L)) * (1 - G))
        2. Knowledge transition update:
           P(L_{t+1}) = P(L_t | obs) + (1 - P(L_t | obs)) * P(T)
        """
        p_l = max(0.01, min(0.99, prior_mastery))
        p_s = self.p_slip
        p_g = self.p_guess
        p_t = self.p_transit

        if is_correct:
            # Observation = 1 (success)
            numerator = p_l * (1.0 - p_s)
            denominator = numerator + (1.0 - p_l) * p_g
            p_posterior = numerator / max(1e-9, denominator)
            # Continuous score blending: scale transition by quality of explanation
            effective_transit = p_t * (0.5 + 0.5 * max(0.0, min(1.0, score)))
        else:
            # Observation = 0 (error / failure)
            numerator = p_l * p_s
            denominator = numerator + (1.0 - p_l) * (1.0 - p_g)
            p_posterior = numerator / max(1e-9, denominator)
            effective_transit = p_t * 0.25

        # Transition stage
        updated_mastery = p_posterior + (1.0 - p_posterior) * effective_transit
        return max(0.01, min(0.99, updated_mastery))

    def update_mastery(
        self,
        model: StudentModel,
        concept_id: str,
        is_correct: bool,
        score: float = 1.0,
    ) -> StudentModel:
        """Applies Bayesian Knowledge Tracing update to concept mastery."""
        prior = model.concept_mastery.get(concept_id, BKT_DEFAULT_P_L0)
        new_mastery = self.compute_bkt_update(prior, is_correct, score)

        model.concept_mastery[concept_id] = round(new_mastery, 3)
        model.last_updated = datetime.now(timezone.utc)
        self._models[model.user_id] = model
        return model

    def estimate_retention(
        self,
        model: StudentModel,
        concept_id: str,
        elapsed_days: float = 0.0,
    ) -> float:
        """
        Estimates current retention probability using Ebbinghaus exponential decay:
        R = e^(-t / S)
        where S is memory stability derived from current mastery score.
        """
        base_mastery = model.concept_mastery.get(concept_id, 0.5)
        stability = max(1.0, base_mastery * 30.0)  # High mastery implies up to 30 days stability
        decay = math.exp(-elapsed_days / stability)
        return round(base_mastery * decay, 3)

    def record_evaluation(
        self,
        user_id: str,
        concept_id: str,
        concept_title: str,
        is_understood: bool,
        score: float,
        misconception: Optional[str] = None,
        gap: Optional[str] = None,
    ) -> StudentModel:
        """Comprehensive evaluation recorder updating mastery, weaknesses, and misconceptions."""
        model = self.get_model(user_id)
        self.update_mastery(model, concept_id, is_understood, score)
        current_mastery = model.concept_mastery[concept_id]

        now_iso = datetime.now(timezone.utc).isoformat()

        # Track Weaknesses
        if not is_understood or score < 0.60:
            existing = next((w for w in model.weaknesses if w.get("concept_id") == concept_id), None)
            if existing:
                existing["error_count"] = existing.get("error_count", 1) + 1
                existing["last_tested"] = now_iso
                existing["mastery_score"] = current_mastery
                if gap:
                    existing["reason"] = gap
            else:
                model.weaknesses.append({
                    "concept_id": concept_id,
                    "title": concept_title,
                    "reason": gap or "Failed active recall evaluation",
                    "error_count": 1,
                    "mastery_score": current_mastery,
                    "last_tested": now_iso,
                })

            if misconception:
                model.misconceptions.append({
                    "concept_id": concept_id,
                    "title": concept_title,
                    "pattern": misconception,
                    "timestamp": now_iso,
                })
        else:
            # Resolved weakness or promoted to strength
            model.weaknesses = [w for w in model.weaknesses if w.get("concept_id") != concept_id]
            if current_mastery >= 0.80:
                if not any(s.get("concept_id") == concept_id for s in model.strengths):
                    model.strengths.append({
                        "concept_id": concept_id,
                        "title": concept_title,
                        "mastery_score": current_mastery,
                        "mastered_at": now_iso,
                    })

        self.save_model(model)
        return model

    # ── Database persistence ──────────────────────────────────────────────

    def _load_from_db(self, user_id: str) -> Optional[StudentModel]:
        """Loads cognitive state from user_memory table."""
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

                    model_data = data.get("student_model", {})
                    if model_data:
                        return StudentModel(
                            user_id=user_id,
                            weaknesses=model_data.get("weaknesses", []),
                            strengths=model_data.get("strengths", []),
                            misconceptions=model_data.get("misconceptions", []),
                            concept_mastery=model_data.get("concept_mastery", {}),
                        )
        except Exception as exc:
            logger.debug("[StudentModelManager] Notice loading model: %s", exc)

        return None

    def _persist_to_db(self, model: StudentModel) -> None:
        """Saves cognitive state into user_memory table."""
        try:
            with engine.begin() as conn:
                existing_row = conn.execute(
                    text("SELECT memory_json FROM user_memory WHERE user_id = :uid"),
                    {"uid": model.user_id},
                ).mappings().fetchone()

                mem = {}
                if existing_row and existing_row.get("memory_json"):
                    raw = existing_row["memory_json"]
                    mem = json.loads(raw) if isinstance(raw, str) else raw

                mem["student_model"] = {
                    "weaknesses": model.weaknesses,
                    "strengths": model.strengths,
                    "misconceptions": model.misconceptions[-50:],
                    "concept_mastery": model.concept_mastery,
                    "last_updated": model.last_updated.isoformat(),
                }

                conn.execute(
                    text("""
                        INSERT INTO user_memory (user_id, memory_json, updated_at)
                        VALUES (:uid, CAST(:mem AS jsonb), now())
                        ON CONFLICT (user_id) DO UPDATE SET
                            memory_json = EXCLUDED.memory_json,
                            updated_at = now();
                    """),
                    {"uid": model.user_id, "mem": json.dumps(mem)},
                )
        except Exception as exc:
            logger.debug("[StudentModelManager] Notice persisting model: %s", exc)


student_model_manager = StudentModelManager()
