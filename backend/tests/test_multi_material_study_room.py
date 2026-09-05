import pytest
from app.services.study_storage import (
    init_session_db,
    save_session_topics,
    get_session_topics,
    save_session_document,
    get_session_documents,
    register_or_update_session,
    get_registry_session,
    delete_registry_session,
    insert_chunks_to_fts,
    search_fts_chunks,
)

@pytest.mark.asyncio
async def test_multi_material_session_flow():
    test_sid = "test_multi_mat_sid_999"
    try:
        init_session_db(test_sid)

        # 1. Create a Blank Room session
        reg = register_or_update_session(
            session_id=test_sid,
            subject="General Study",
            title="New Study Workspace",
            status="ready"
        )
        assert reg["title"] == "New Study Workspace"
        assert reg.get("document_count", 0) == 0

        # 2. Upload Material 1: "Chemistry_Textbook.pdf"
        save_session_document(test_sid, "doc_1", "Chemistry_Textbook.pdf", "/tmp/chem.pdf", status="fully_processed", page_count=50)
        reg = register_or_update_session(
            session_id=test_sid,
            subject="Chemistry",
            title="Chemistry Study Room",
            status="text_ready",
            document_name="Chemistry_Textbook.pdf"
        )
        assert reg["title"] == "Chemistry Study Room"
        assert reg["document_count"] == 1
        assert "Chemistry_Textbook.pdf" in reg["documents"]

        topics_doc1 = [
            {"id": "t1", "title": "Chemical Equilibrium", "summary": "Dynamic equilibrium principles", "difficulty": "Intermediate", "key_concepts": ["Le Chatelier"], "estimated_study_time": "20 mins"},
            {"id": "t2", "title": "Acids and Bases", "summary": "pH and buffer solutions", "difficulty": "Intermediate", "key_concepts": ["pH", "pOH"], "estimated_study_time": "25 mins"},
        ]
        save_session_topics(test_sid, topics_doc1, append=False)
        assert len(get_session_topics(test_sid)) == 2

        insert_chunks_to_fts(test_sid, "doc_1", [
            {"chunk_id": "c1_1", "page": 10, "source_type": "text", "content": "[Doc: Chemistry_Textbook.pdf | Page 10 | Type: text] Le Chatelier's principle states that if a dynamic equilibrium is disturbed, the position of equilibrium shifts to counteract the change."}
        ])

        # 3. Upload Material 2 into the SAME session: "Teacher_Notes.pdf"
        save_session_document(test_sid, "doc_2", "Teacher_Notes.pdf", "/tmp/notes.pdf", status="fully_processed", page_count=10)
        reg = register_or_update_session(
            session_id=test_sid,
            subject="Chemistry",
            title="Formula Sheet Study Room", # should PRESERVE "Chemistry Study Room"
            status="text_ready",
            document_name="Teacher_Notes.pdf"
        )
        # Title must be preserved because it wasn't a placeholder
        assert reg["title"] == "Chemistry Study Room"
        assert reg["document_count"] == 2
        assert "Teacher_Notes.pdf" in reg["documents"]

        topics_doc2 = [
            {"id": "t3", "title": "Equilibrium Constant Shortcut", "summary": "Tips for solving Kp and Kc", "difficulty": "Advanced", "key_concepts": ["Kp", "Kc"], "estimated_study_time": "10 mins"},
            {"id": "t4", "title": "Chemical Equilibrium", "summary": "Duplicate title from textbook", "difficulty": "Easy", "key_concepts": []},
        ]
        # Append topics without duplicate title
        merged = save_session_topics(test_sid, topics_doc2, append=True)
        # Should now have 3 topics (t1, t2, t3) - duplicate "Chemical Equilibrium" skipped
        assert len(merged) == 3
        titles = [t["title"] for t in merged]
        assert "Equilibrium Constant Shortcut" in titles
        assert "Acids and Bases" in titles
        assert "Chemical Equilibrium" in titles

        insert_chunks_to_fts(test_sid, "doc_2", [
            {"chunk_id": "c2_1", "page": 2, "source_type": "text", "content": "[Doc: Teacher_Notes.pdf | Page 2 | Type: text] Shortcut for chemical equilibrium: Kp = Kc * (RT)^delta_n where delta_n is moles of gaseous products minus reactants."}
        ])

        # 4. Check that get_session_documents returns both
        docs = get_session_documents(test_sid)
        assert len(docs) == 2
        assert docs[0]["filename"] == "Chemistry_Textbook.pdf"
        assert docs[1]["filename"] == "Teacher_Notes.pdf"

        # 5. Search across ALL materials in that session
        results = search_fts_chunks(test_sid, "equilibrium")
        assert len(results) >= 2
        doc_sources = [r["content"] for r in results]
        assert any("Doc: Chemistry_Textbook.pdf" in c for c in doc_sources)
        assert any("Doc: Teacher_Notes.pdf" in c for c in doc_sources)

    finally:
        delete_registry_session(test_sid)
