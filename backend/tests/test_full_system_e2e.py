"""
Comprehensive End-to-End System Health and Functional Verification Suite.
Validates all backend APIs, database models, cloud integrations (Neon, Pinecone, S3, Gemini),
and core learning workflows.
"""
import sys
import os
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import asyncio
from app.core.config import get_settings
from app.core import database as db
from app.rag.storage.s3_store import s3_store
from app.rag.gemini_client import gemini
from app.rag.storage import active_vector_store
from app.rag.study_plan_generator import generate_study_plan, generate_day_study_notes

settings = get_settings()

def run_checks():
    results = {}
    print("\n" + "="*60)
    print("[AUDIT] DEEPTUTOR FULL-SYSTEM FUNCTIONAL AUDIT")
    print("="*60 + "\n")

    # 1. Database Connection (Neon Cloud PostgreSQL)
    print("1. Testing Neon Cloud PostgreSQL Connection...")
    test_user_id = None
    try:
        # Create or fetch a test student user with valid foreign keys
        test_email = "audit_system_test@deeptutor.ai"
        user = db.get_user_by_email(test_email)
        if not user:
            user = db.create_user(
                username="audit_tester",
                email=test_email,
                password_hash="system_hash_123"
            )
        test_user_id = user["id"]
        results["PostgreSQL (Neon)"] = "PASSED (Connected & Queryable)"
        print(f"   [OK] PostgreSQL query successful. Active User ID: {test_user_id}")
    except Exception as e:
        results["PostgreSQL (Neon)"] = f"FAILED: {e}"
        print(f"   [ERROR] PostgreSQL: {e}")

    # 2. Cloud Knowledge Graph in PostgreSQL
    print("\n2. Testing Cloud Knowledge Graph CRUD...")
    try:
        test_topic = f"audit_topic_{test_user_id[:8]}"
        test_entities = {"ml": {"name": "Machine Learning", "type": "concept"}}
        test_relations = {"ml___REL___ai": {"source_entity": "Machine Learning", "target_entity": "AI", "type": "SUBFIELD_OF"}}
        test_triplets = [{"head": "Machine Learning", "relation": "SUBFIELD_OF", "tail": "Artificial Intelligence", "confidence": 0.95}]

        db.save_knowledge_graph(test_topic, test_entities, test_relations, test_triplets, user_id=test_user_id)
        saved = db.get_knowledge_graph(test_topic)
        assert saved is not None, "Failed to retrieve saved graph"
        assert "ml" in saved["entities"], "Entity missing from saved graph"
        assert len(saved["triplets"]) == 1, "Triplet count mismatch"
        db.delete_knowledge_graph(test_topic)
        results["Cloud Knowledge Graph"] = "PASSED (Save, Load, Delete in Neon DB)"
        print("   [OK] Knowledge Graph cloud persistence successful.")
    except Exception as e:
        results["Cloud Knowledge Graph"] = f"FAILED: {e}"
        print(f"   [ERROR] Knowledge Graph: {e}")

    # 3. AWS S3 Cloud Storage
    print("\n3. Testing AWS S3 Cloud Storage Bucket...")
    try:
        assert s3_store.is_configured(), "S3 is not configured"
        test_key = f"test_system_audit/{test_user_id}/health_check.txt"
        test_content = b"DeepTutor S3 Cloud Storage Verification Check"
        uploaded_key = s3_store.upload_bytes(test_content, test_key, "text/plain")
        assert uploaded_key == test_key, "Uploaded S3 key mismatch"
        presigned_url = s3_store.get_presigned_download_url(test_key)
        assert presigned_url and "https://" in presigned_url, "Invalid presigned URL"
        s3_store.delete_file(test_key)
        results["AWS S3 Storage"] = f"PASSED (Upload, Presign, Delete in {settings.AWS_S3_BUCKET_NAME})"
        print("   [OK] AWS S3 operations verified.")
    except Exception as e:
        results["AWS S3 Storage"] = f"FAILED: {e}"
        print(f"   [ERROR] S3: {e}")

    # 4. Pinecone Vector Database
    print("\n4. Testing Pinecone Cloud Vector Database...")
    try:
        results_list = active_vector_store.search("system_audit", [0.0] * 3072, top_k=1, min_score=0.0)
        results["Pinecone Vector DB"] = f"PASSED (Index: {settings.PINECONE_INDEX_NAME}, Connected)"
        print(f"   [OK] Pinecone cloud index connected successfully.")
    except Exception as e:
        results["Pinecone Vector DB"] = f"FAILED: {e}"
        print(f"   [ERROR] Vector Store: {e}")

    # 5. Gemini AI LLM Client
    print("\n5. Testing Gemini AI LLM Engine...")
    try:
        reply = asyncio.run(gemini.chat([{"role": "user", "content": "Say 'DeepTutor AI is fully operational.' in 6 words."}]))
        assert len(reply) > 5, "Gemini reply too short"
        results["Gemini AI LLM"] = f"PASSED (Model: {settings.GEMINI_CHAT_MODEL})"
        print(f"   [OK] Gemini responded: {reply.strip()[:60]}...")
    except Exception as e:
        results["Gemini AI LLM"] = f"FAILED: {e}"
        print(f"   [ERROR] Gemini: {e}")

    # 6. Study Plan & AI Notes Generator
    print("\n6. Testing Study Plan & Notes Generator...")
    try:
        plan = asyncio.run(generate_study_plan(
            user_id=test_user_id,
            topic_id="ml-fundamentals",
            target_date="2026-08-25",
            hours_per_day=2.0
        ))
        assert "schedule" in plan and len(plan["schedule"]) > 0, "Empty study plan schedule"
        first_day = plan["schedule"][0]
        notes = asyncio.run(generate_day_study_notes(
            user_id=test_user_id,
            topic_id="ml-fundamentals",
            day_topic=first_day.get("topic", "Introduction to ML"),
            key_concepts=first_day.get("key_concepts", [])
        ))
        assert len(notes) > 50, "Study notes too short"
        results["Study Plan & Notes"] = f"PASSED (Generated {len(plan['schedule'])}-day plan & AI notes)"
        print(f"   [OK] Study Plan generator verified ({len(plan['schedule'])} days).")
    except Exception as e:
        results["Study Plan & Notes"] = f"FAILED: {e}"
        print(f"   [ERROR] Study Plan: {e}")

    # 7. Print Final Summary Table
    print("\n" + "="*60)
    print("SYSTEM AUDIT SUMMARY TABLE")
    print("="*60)
    all_passed = True
    for component, status in results.items():
        print(f"{component:28} : {status}")
        if "FAILED" in status:
            all_passed = False
    print("="*60 + "\n")
    if all_passed:
        print("[SUCCESS] ALL SYSTEM COMPONENTS ARE 100% OPERATIONAL!\n")
    return all_passed

if __name__ == "__main__":
    success = run_checks()
    sys.exit(0 if success else 1)
