# Good vs. Bad Implementation Patterns

This document contrasts anti-patterns with production-grade implementations.

---

### 1. Parameterization & Generalization

#### ❌ Anti-Pattern (Hardcoding Domain Words or Thresholds)
```python
# BAD: Hardcoding specific topics or academic classifications in general code
def retrieve_relevant_chunks(query: str, session):
    if "forest" in query.lower():
        return session.query(KnowledgeChunk).filter(KnowledgeChunk.topic == "Forest types in India").all()
    ...
```

#### ✅ Production-Grade (Dynamic Keyword Extraction & Hybrid Scoring)
```python
# GOOD: Generic stopword stripping, dynamic token weighting, resilient fallback
STOPWORDS = {"what", "are", "the", "in", "of", "is", "a", "an", "and", "or"}

def extract_meaningful_tokens(query: str) -> List[str]:
    cleaned = re.sub(r"[^\w\s]", " ", query.lower())
    return [t for t in cleaned.split() if len(t) > 2 and t not in STOPWORDS]

def retrieve_relevant_chunks(tokens: List[str], session, document_id: str):
    # Vector similarity + BM25 keyword matching with fallback to all document chunks
    ...
```

---

### 2. Configuration & Environment Variables

#### ❌ Anti-Pattern (Inline Secrets and Paths)
```python
# BAD: Hardcoded port, API key, and developer absolute directory
DB_URL = "postgresql://postgres:secret123@localhost:5432/deeptutor"
UPLOAD_DIR = "C:/Users/lenovo/Desktop/ASIMOVX/uploads"
```

#### ✅ Production-Grade (Environment-Driven with Sensible Defaults)
```python
# GOOD: Pydantic BaseSettings or os.getenv with dynamic path resolution
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DATABASE_URL must be configured in environment or .env file")
```

---

### 3. Fail-Safe vs. Silent Failure

#### ❌ Anti-Pattern (Silent Fallback or Empty Response)
```python
# BAD: Empty result causes downstream component to assume user is out-of-scope
if not matches:
    return []
```

#### ✅ Production-Grade (Resilient Candidate Fallback)
```python
# GOOD: Fall back gracefully to broader candidate set while logging diagnostic info
if not matches and document_id:
    logger.warning("Targeted filter yielded 0 chunks; falling back to all document chunks for document %s", document_id)
    matches = session.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document_id).all()
```
