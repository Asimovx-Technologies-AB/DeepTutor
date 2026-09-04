"""
User Memory System — Persistent Learning Profile & Long-term Episodic Memory for Indie Tutor.
Maintains:
1. Student profile & preferred learning style
2. Active academic goals & exam targets
3. Studied topics & mastery levels
4. Known learning struggles / focus areas
5. Auto-extraction of student learning facts from conversation
"""
import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

from app.rag.ollama_client import ollama

MEMORY_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "user_memory.json"


@dataclass
class StudentMemory:
    user_id: str
    name: str = "Student"
    learning_style: str = "Step-by-step with clear examples"
    active_goals: List[str] = field(default_factory=list)
    studied_topics: List[Dict[str, Any]] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    facts: List[str] = field(default_factory=list)
    last_active: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class UserMemoryStore:
    """
    Persistent store for student memory and learning history.
    Saves to JSON file on disk and auto-loads on startup.
    """

    def __init__(self):
        self._memory_cache: Dict[str, StudentMemory] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        """Loads persistent memories from disk."""
        try:
            if MEMORY_FILE_PATH.exists():
                with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    for uid, mdata in raw_data.items():
                        self._memory_cache[uid] = StudentMemory(
                            user_id=uid,
                            name=mdata.get("name", "Student"),
                            learning_style=mdata.get("learning_style", "Step-by-step with clear examples"),
                            active_goals=mdata.get("active_goals", []),
                            studied_topics=mdata.get("studied_topics", []),
                            weaknesses=mdata.get("weaknesses", []),
                            facts=mdata.get("facts", []),
                            last_active=mdata.get("last_active", datetime.utcnow().isoformat()),
                        )
        except Exception as e:
            print(f"[UserMemory] Error loading memory file: {e}")

    def _save_to_disk(self):
        """Persists memories to disk."""
        try:
            MEMORY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            serializable = {uid: asdict(mem) for uid, mem in self._memory_cache.items()}
            with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[UserMemory] Error saving memory file: {e}")

    def get_memory(self, user_id: str = "default_user", user_name: Optional[str] = None) -> StudentMemory:
        """Retrieves or initializes a student memory record."""
        if user_id not in self._memory_cache:
            self._load_from_disk()

        if user_id not in self._memory_cache:
            name = user_name or "Student"
            self._memory_cache[user_id] = StudentMemory(
                user_id=user_id,
                name=name,
                active_goals=["Master academic coursework", "Build strong conceptual foundations"],
            )
            self._save_to_disk()
        elif user_name and user_name != "Student" and self._memory_cache[user_id].name != user_name:
            self._memory_cache[user_id].name = user_name
            self._save_to_disk()

        return self._memory_cache[user_id]


    def record_studied_topic(self, user_id: str, topic_title: str, subject: str):
        """Records a topic studied by the user with timestamp."""
        mem = self.get_memory(user_id)
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

        # Check if topic exists
        existing = next((t for t in mem.studied_topics if t.get("title") == topic_title), None)
        if existing:
            existing["last_reviewed"] = now_str
            existing["review_count"] = existing.get("review_count", 1) + 1
        else:
            mem.studied_topics.append({
                "title": topic_title,
                "subject": subject,
                "first_studied": now_str,
                "last_reviewed": now_str,
                "review_count": 1,
            })

        # Keep last 25 topics
        if len(mem.studied_topics) > 25:
            mem.studied_topics = mem.studied_topics[-25:]

        mem.last_active = datetime.utcnow().isoformat()
        self._save_to_disk()

    def record_weakness(self, user_id: str, concept: str):
        """Records a concept where the student requested additional explanation or struggled."""
        mem = self.get_memory(user_id)
        clean_concept = concept.strip()
        if clean_concept and clean_concept not in mem.weaknesses:
            mem.weaknesses.append(clean_concept)
            if len(mem.weaknesses) > 15:
                mem.weaknesses = mem.weaknesses[-15:]
            self._save_to_disk()

    def add_fact(self, user_id: str, fact: str):
        """Adds a permanent note or preference to student memory."""
        mem = self.get_memory(user_id)
        clean_fact = fact.strip()
        if clean_fact and clean_fact not in mem.facts:
            mem.facts.append(clean_fact)
            if len(mem.facts) > 20:
                mem.facts = mem.facts[-20:]
            self._save_to_disk()

    def set_learning_style(self, user_id: str, style: str):
        mem = self.get_memory(user_id)
        mem.learning_style = style.strip()
        self._save_to_disk()

    def add_goal(self, user_id: str, goal: str):
        mem = self.get_memory(user_id)
        clean_goal = goal.strip()
        if clean_goal and clean_goal not in mem.active_goals:
            mem.active_goals.append(clean_goal)
            self._save_to_disk()

    def clear_memory(self, user_id: str):
        """Resets memory for a specific student."""
        if user_id in self._memory_cache:
            del self._memory_cache[user_id]
            self._save_to_disk()

    def format_memory_for_prompt(self, user_id: str = "default_user") -> str:
        """
        Formats user memory into a concise, high-value context block for the AI tutor.
        """
        mem = self.get_memory(user_id)
        lines = []
        lines.append(f"Student Name: {mem.name}")
        lines.append(f"Preferred Learning Style: {mem.learning_style}")

        if mem.active_goals:
            lines.append("Active Academic Goals: " + ", ".join(mem.active_goals[-3:]))

        if mem.weaknesses:
            lines.append("Concepts Needing Focus/Reinforcement: " + ", ".join(mem.weaknesses[-4:]))

        if mem.studied_topics:
            recent_titles = [t["title"] for t in mem.studied_topics[-4:]]
            lines.append("Recently Studied Topics: " + ", ".join(recent_titles))

        if mem.facts:
            lines.append("Known Student Facts & Preferences: " + "; ".join(mem.facts[-4:]))

        return "\n".join(lines)

    async def auto_extract_and_update(self, user_id: str, user_message: str, history: Optional[List[Dict[str, str]]] = None):
        """
        Analyzes student message with Gemini in the background to automatically
        discover new learning preferences, exam deadlines, or conceptual struggles.
        """
        msg_lower = user_message.lower()

        # Quick heuristic pre-filter to avoid unnecessary LLM calls on simple greetings
        trigger_keywords = [
            "exam", "test", "quiz", "struggle", "confused", "prefer", "i like",
            "explain like", "dont understand", "don't understand", "hard for me",
            "my goal", "preparing for", "studying for", "i am", "visual", "step by step"
        ]

        if not any(kw in msg_lower for kw in trigger_keywords):
            return

        prompt = (
            "You are a student memory extraction engine. Analyze this student message:\n"
            f"\"{user_message}\"\n\n"
            "Extract any learning preferences, academic goals, or struggle concepts in JSON format:\n"
            "{\n"
            "  \"new_preference\": \"string or null\",\n"
            "  \"new_goal\": \"string or null\",\n"
            "  \"struggle_concept\": \"string or null\",\n"
            "  \"student_fact\": \"string or null\"\n"
            "}"
        )

        try:
            res_text = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.1)
            # Parse JSON
            cleaned = res_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned.rsplit("\n", 1)[0]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()

            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1:
                data = json.loads(cleaned[start_idx : end_idx + 1])
                if data.get("new_preference"):
                    self.set_learning_style(user_id, data["new_preference"])
                if data.get("new_goal"):
                    self.add_goal(user_id, data["new_goal"])
                if data.get("struggle_concept"):
                    self.record_weakness(user_id, data["struggle_concept"])
                if data.get("student_fact"):
                    self.add_fact(user_id, data["student_fact"])
        except Exception as e:
            print(f"[UserMemory] Auto extraction warning: {e}")


# Singleton instance
user_memory_store = UserMemoryStore()
