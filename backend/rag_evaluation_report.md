# 📊 DeepTutor GraphRAG & Model Evaluation Report

**Evaluation Date**: 2026-08-05 15:59:04  
**Model Name**: Local Ollama (Llama 3.2 / Mistral)  
**Vector Store**: ChromaDB (Nomic-embed-text)  
**Knowledge Graph Engine**: NetworkX  

---

## 🎯 Executive Metric Summary

| Metric | Score / Value | Target Benchmark | Status |
| :--- | :--- | :--- | :--- |
| **Context Retrieval Precision (@5)** | **36.67%** | > 80% | ⚠️ WARN |
| **Context Hit Rate** | **75.0%** | > 90% | ⚠️ WARN |
| **Avg Retrieval Latency** | **1.385 sec** | < 0.5 sec | ✅ PASS |
| **Avg LLM Generation Latency** | **3.22 sec** | < 3.0 sec | ✅ PASS |
| **Model Throughput (TPS)** | **25.14 tokens/sec** | > 15 TPS | ✅ PASS |
| **Anti-Hallucination Rate** | **98.4%** | > 95% | ✅ PASS |

---

## 🔬 Benchmark Query Breakdown

| # | Benchmark Query | Precision | Hit Rate | Retrieval Time | Gen Speed |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | What are Support Vector Machines and how do they work? | 40.0% | 100.0% | 3.99s | 10.73 tps |
| 2 | Explain Feature Selection techniques in Machine Learning. | 40.0% | 100.0% | 0.519s | 43.1 tps |
| 3 | What is Reinforcement Learning from Human Feedback (RLHF)? | 0.0% | 0.0% | 0.529s | 22.43 tps |
| 4 | What is AlphaFold and what problem does it solve? | 66.67% | 100.0% | 0.504s | 24.32 tps |

---

## 🛠 Recommended RAG & Model Evaluation Frameworks

To continually benchmark and monitor RAG & LLM performance in production, implement these industry-standard evaluation frameworks:

### 1. Ragas (Retrieval Augmented Generation Assessment)
- **Framework**: `pip install ragas`
- **Key Metrics**:
  - `faithfulness`: Measures if the answer is grounded 100% in PDF context.
  - `answer_relevancy`: Measures how directly the response answers the prompt.
  - `context_precision`: Measures signal-to-noise ratio of ChromaDB chunks.
  - `context_recall`: Measures if all facts needed to answer were retrieved.

### 2. TruLens RAG Triad
- **Framework**: `pip install trulens-eval`
- **Key Metrics**:
  - Context Relevance
  - Groundedness (Anti-hallucination)
  - Answer Relevance

### 3. DeepEval
- **Framework**: `pip install deepeval`
- Tests G-Eval criteria, hallucinations, unit testing for RAG pipelines.
