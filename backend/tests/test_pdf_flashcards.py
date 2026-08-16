import asyncio
import sys
import pytest
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.rag.storage import active_vector_store
from app.rag.vector_store import vector_store
from app.rag.flashcard_generator import generate_flashcards_for_section


from app.core import database as db


@pytest.mark.asyncio
async def test_pdf_flashcards_generation():
    topic_id = "test_pdf_flashcards_topic"
    user_id = "test_user_id"

    # Register test session in DB so user ownership validation passes
    db.create_session(user_id, topic_id, "Test PDF Flashcards Session")

    # Add dummy PDF chunks with page metadata to vector store
    dummy_chunks = [
        {
            "id": "c1",
            "text": "Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin.",
            "metadata": {"source": "ml_guide.pdf", "page": 42}
        },
        {
            "id": "c2",
            "text": "Feature selection techniques include Filter methods, Wrapper methods, and Embedded methods such as SVM-RFE.",
            "metadata": {"source": "ml_guide.pdf", "page": 43}
        }
    ]
    dummy_embeddings = [[0.1] * 768 for _ in range(2)]

    namespaced_topic = f"sec_{user_id.replace('-', '_')}_{topic_id.replace('-', '_')}"
    active_vector_store.add_chunks(namespaced_topic, dummy_chunks, dummy_embeddings)

    from app.rag.ollama_client import ollama
    ollama_ok = await ollama.is_available()

    print(f"Generating flashcards for namespaced topic '{namespaced_topic}'...")
    cards = await generate_flashcards_for_section(section_id=topic_id, user_id=user_id)

    print(f"Generated {len(cards)} flashcards from uploaded PDF context (Ollama connected: {ollama_ok}).")
    if ollama_ok:
        assert len(cards) > 0, "Expected generated flashcards when Ollama is online"
    else:
        assert isinstance(cards, list), "Expected list response"

    # Cleanup
    active_vector_store.delete_collection(namespaced_topic)
    print("PDF Flashcards generation test passed successfully!")


if __name__ == "__main__":
    asyncio.run(test_pdf_flashcards_generation())
