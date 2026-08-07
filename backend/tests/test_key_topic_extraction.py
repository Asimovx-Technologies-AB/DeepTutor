import sys
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.rag.document_processor import extract_key_topics


def test_extract_key_topics_basic():
    dummy_chunks = [
        {
            "text": "1.1 Support Vector Machines\nSupport Vector Machines (SVM) are supervised learning models with associated learning algorithms that analyze data for classification and regression analysis.",
            "metadata": {"source": "machine_learning.pdf", "page": 1}
        },
        {
            "text": "### Feature Selection\nFeature selection techniques include Filter Methods, Wrapper Methods, and Embedded Methods like SVM-RFE.",
            "metadata": {"source": "machine_learning.pdf", "page": 2}
        },
        {
            "text": "Gradient Descent is an first-order iterative optimization algorithm for finding a local minimum of a differentiable function.",
            "metadata": {"source": "machine_learning.pdf", "page": 3}
        }
    ]

    topics = extract_key_topics(dummy_chunks)
    print("Extracted topics:", topics)
    assert len(topics) > 0, "Expected at least 1 extracted topic"
    
    topics_lower = [t.lower() for t in topics]
    assert any("support vector machines" in t or "svm" in t for t in topics_lower), "Expected SVM in extracted topics"
    assert any("feature selection" in t for t in topics_lower), "Expected Feature Selection in extracted topics"
    print("test_extract_key_topics_basic passed successfully!")


if __name__ == "__main__":
    test_extract_key_topics_basic()
