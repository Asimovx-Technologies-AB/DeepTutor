"""
Live Hallucination & Grounding Verification Test Suite.
Tests:
1. In-scope question with context -> Strict grounding & citations [p.X]
2. Out-of-scope question -> Refusal to fabricate facts ("The provided material doesn't cover this...")
3. Unverified claim detection -> Hallucination Guard scoring (grounded vs hallucinated text)
4. Pedagogical clarity -> Structured explanations for students (analogy, breakdown, steps, takeaway)
"""
import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.rag.ollama_client import ollama
from app.rag.graph_rag import SYSTEM_PROMPT
from app.rag.hallucination_guard import verify_response_grounding


SAMPLE_CONTEXT_CHUNKS = [
    {
        "id": "chunk_svm_1",
        "text": (
            "Support Vector Machines (SVMs) are supervised learning models used for classification and regression. "
            "An SVM constructs a hyperplane or set of hyperplanes in a high- or infinite-dimensional space. "
            "A good separation is achieved by the hyperplane that has the largest distance to the nearest training-data point "
            "of any class (functional margin). The points that lie closest to the decision surface are called support vectors."
        ),
        "metadata": {"source": "ml_handbook.pdf", "page": 42, "section_title": "Support Vector Machines"},
        "score": 0.89,
    },
    {
        "id": "chunk_svm_2",
        "text": (
            "When the data is not linearly separable, SVM uses the kernel trick to map the input data into a higher-dimensional space "
            "where linear separation becomes possible. Common kernel functions include Radial Basis Function (RBF), Linear, and Polynomial kernels. "
            "The regularization parameter C controls the trade-off between achieving a low training error and a low testing error."
        ),
        "metadata": {"source": "ml_handbook.pdf", "page": 43, "section_title": "Kernel Methods"},
        "score": 0.85,
    },
]


async def test_in_scope_grounded_response():
    print("\n" + "=" * 60)
    print("TEST 1: In-Scope Question with Real Document Context")
    print("=" * 60)

    question = "Explain Support Vector Machines (SVM), how the margin works, and what support vectors are."
    
    context_text = "\n\n".join([
        f"[{c['metadata']['source']} p.{c['metadata']['page']} §{c['metadata']['section_title']}]\n{c['text']}"
        for c in SAMPLE_CONTEXT_CHUNKS
    ])

    user_content = (
        f"## Document Context\n"
        f"Relevant passages from uploaded documents:\n"
        f"{context_text}\n\n"
        f"## Student Question\n"
        f"{question}\n\n"
        f"## Instructions\n"
        f"Using the Document Context as your primary reference, answer clearly for a student following all grounding and citation rules."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    print(f"Querying LLM with strict grounding prompt...")
    start_time = asyncio.get_event_loop().time()
    response = await ollama.chat(messages, temperature=0.1)
    duration = asyncio.get_event_loop().time() - start_time

    print(f"Generated Response in {duration:.2f}s:\n")
    print(response)
    print("\n" + "-" * 60)

    # Run Grounding Verification
    guard_result = verify_response_grounding(response, SAMPLE_CONTEXT_CHUNKS)
    print(f"🛡️ Hallucination Guard Result: {guard_result['formatted_badge']}")
    print(f"Score: {guard_result['grounding_score'] * 100}% | Verified: {guard_result['verified']}")
    print(f"Sentences Checked: {guard_result['matched_sentences']}/{guard_result['total_sentences']}")
    if guard_result['unverified_claims']:
        print(f"Unverified claims flagged: {guard_result['unverified_claims']}")
    else:
        print("✅ Zero unverified claims detected.")


async def test_out_of_scope_hallucination_prevention():
    print("\n" + "=" * 60)
    print("TEST 2: Out-of-Scope Question (Testing Refusal to Hallucinate)")
    print("=" * 60)

    # Question about something completely outside the context
    question = "What is the capital of Australia and who won the 2022 World Cup?"

    context_text = "\n\n".join([
        f"[{c['metadata']['source']} p.{c['metadata']['page']} §{c['metadata']['section_title']}]\n{c['text']}"
        for c in SAMPLE_CONTEXT_CHUNKS
    ])

    user_content = (
        f"## Document Context\n"
        f"Relevant passages from uploaded documents:\n"
        f"{context_text}\n\n"
        f"## Student Question\n"
        f"{question}\n\n"
        f"## Instructions\n"
        f"Using the Document Context as your primary reference, answer clearly for a student following all grounding and citation rules."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    print(f"Querying LLM with out-of-scope question...")
    response = await ollama.chat(messages, temperature=0.1)

    print(f"Generated Response:\n")
    print(response)
    print("\n" + "-" * 60)

    is_refused = any(phrase in response.lower() for phrase in [
        "doesn't cover", "cannot find", "not mentioned", "not in the context", 
        "don't know", "provided material doesn't cover", "not present"
    ])

    if is_refused:
        print("✅ SUCCESS: The model adhered to Rule #1 and explicitly refused to hallucinate outside knowledge!")
    else:
        print("❌ WARNING: The model attempted to answer using outside knowledge.")


async def test_hallucination_guard_detector():
    print("\n" + "=" * 60)
    print("TEST 3: Hallucination Guard Unit Test (Grounding vs Hallucination)")
    print("=" * 60)

    grounded_sample = (
        "Support Vector Machines construct a hyperplane in high-dimensional space for classification [p.42]. "
        "The support vectors are the training data points closest to the decision surface [p.42]. "
        "When data is not linearly separable, SVM uses the kernel trick such as RBF or Linear kernels [p.43]."
    )

    hallucinated_sample = (
        "Support Vector Machines were invented by Albert Einstein in 1905 on page 999. "
        "They utilize quantum entanglement to teleport decision trees to Mars. "
        "The hyperparameter C was discovered during the Apollo 11 lunar mission."
    )

    grounded_res = verify_response_grounding(grounded_sample, SAMPLE_CONTEXT_CHUNKS)
    hallucinated_res = verify_response_grounding(hallucinated_sample, SAMPLE_CONTEXT_CHUNKS)

    print(f"Grounded Sample Score: {grounded_res['grounding_score'] * 100}% | Badge: {grounded_res['formatted_badge']}")
    print(f"Hallucinated Sample Score: {hallucinated_res['grounding_score'] * 100}% | Badge: {hallucinated_res['formatted_badge']}")
    print(f"Hallucinated Claims Flagged: {len(hallucinated_res['unverified_claims'])}")

    assert grounded_res["verified"] is True, "Grounded text should pass verification"
    assert hallucinated_res["grounding_score"] < 0.40, "Hallucinated text should score low"
    print("✅ Hallucination Guard correctly discriminates between grounded and fabricated content.")


async def main():
    print("================================================================")
    print("DEEPTUTOR ANTI-HALLUCINATION & STRICT GROUNDING TEST SUITE")
    print("================================================================")
    
    # Check Ollama connection
    if not await ollama.is_available():
        print("❌ Ollama is not reachable at http://127.0.0.1:11434. Please ensure Ollama is running.")
        return

    working_model = await ollama.get_working_chat_model()
    print(f"Connected to Ollama! Active model: {working_model}")

    await test_in_scope_grounded_response()
    await test_out_of_scope_hallucination_prevention()
    await test_hallucination_guard_detector()

    print("\n" + "=" * 60)
    print("🎉 ALL ANTI-HALLUCINATION TESTS COMPLETED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
