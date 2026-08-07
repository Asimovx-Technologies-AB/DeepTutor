import asyncio
import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.rag.vector_store import vector_store
from app.rag.flashcard_generator import generate_flashcards_for_section


async def test_pdf_flashcards_generation():
    topic_id = "test_pdf_flashcards_topic"
    user_id = "test_user_id"

    # Add dummy PDF chunks with page metadata to vector store
    dummy_chunks = [
        {
            "text": "Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin.",
            "metadata": {"source": "ml_guide.pdf", "page": 42}
        },
        {
            "text": "Feature selection techniques include Filter methods, Wrapper methods, and Embedded methods such as SVM-RFE.",
            "metadata": {"source": "ml_guide.pdf", "page": 43}
        }
    ]
    dummy_embeddings = [[0.1] * 384 for _ in range(2)]

    namespaced_topic = f"{user_id.replace('-', '_')}_{topic_id.replace('-', '_')}"
    vector_store.add_chunks(namespaced_topic, dummy_chunks, dummy_embeddings)

    print(f"Generating flashcards for namespaced topic '{namespaced_topic}'...")
    cards = await generate_flashcards_for_section(section_id=topic_id, user_id=user_id)

    print(f"Generated {len(cards)} flashcards from uploaded PDF context.")
    assert len(cards) > 0, "Expected generated flashcards, got 0"

    for c in cards:
        print(f"  Front: {c['front']}")
        print(f"  Back:  {c['back']}")

    # Cleanup
    vector_store.delete_topic(namespaced_topic)
    print("PDF Flashcards generation test passed successfully!")


if __name__ == "__main__":
    asyncio.run(test_pdf_flashcards_generation())
