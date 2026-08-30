"""Regression tests for the document-first, per-user learning flow."""

from app.rag.section_scope import get_section_collection_id, user_owns_section
from app.core import database as db


def test_curriculum_like_ids_are_namespaced_per_user():
    assert get_section_collection_id("user-a", "phys-10-1") == "sec_user-a_phys-10-1"
    assert get_section_collection_id("user-b", "phys-10-1") == "sec_user-b_phys-10-1"


def test_section_requires_user_owned_material(monkeypatch):
    monkeypatch.setattr(db, "get_documents_for_user_and_topic", lambda user_id, section_id: [])
    monkeypatch.setattr(db, "get_documents_for_user", lambda user_id: [])
    monkeypatch.setattr(db, "get_sessions_for_user", lambda user_id: [])

    assert user_owns_section("user-a", "phys-10-1") is False
    assert user_owns_section("user-a", "general") is False


def test_owned_document_grants_only_its_owner(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_documents_for_user_and_topic",
        lambda user_id, section_id: [{"id": "doc-1"}] if user_id == "owner" else [],
    )
    monkeypatch.setattr(db, "get_documents_for_user", lambda user_id: [])
    monkeypatch.setattr(db, "get_sessions_for_user", lambda user_id: [])

    assert user_owns_section("owner", "section-1") is True
    assert user_owns_section("other-user", "section-1") is False
