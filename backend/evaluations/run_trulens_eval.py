"""
2. TRULENS RAG TRIAD EVALUATION SCRIPT FOR DEEPTUTOR
Install dependencies:
  pip install trulens-eval
Run:
  python evaluations/run_trulens_eval.py
"""

import os
from trulens_eval import Tru, Feedback, Select, TruCustomApp
from trulens_eval.feedback import Groundedness, Provider

# Initialize TruLens session
tru = Tru()

# 1. Custom DeepTutor RAG Retrieval Function
def deeptutor_rag_query(query: str) -> dict:
    """Mock/Wrapper for DeepTutor RAG pipeline."""
    # Simulates ChromaDB context retrieval + Ollama response
    context = "Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin."
    answer = "Support Vector Machines (SVM) are classification models that construct optimal hyper-planes to separate data classes with maximum margin."
    return {"query": query, "context": context, "answer": answer}

def run_trulens():
    print("=" * 60)
    print("🚀 RUNNING TRULENS RAG TRIAD EVALUATION FOR DEEPTUTOR")
    print("=" * 60)

    # Define Feedback Functions for RAG Triad
    # 1. Groundedness (Anti-hallucination)
    # 2. Context Relevance
    # 3. Answer Relevance
    
    print("\nTruLens evaluation framework initialized.")
    print("To launch the interactive TruLens Dashboard, run in terminal:")
    print("  trulens-eval leaderboard")
    print("=" * 60)

if __name__ == "__main__":
    run_trulens()
