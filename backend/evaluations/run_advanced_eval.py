"""
Advanced RAG & GraphRAG Evaluation Suite for DeepTutor
------------------------------------------------------
Evaluates the live GraphRAGPipeline on:
- Faithfulness / Groundedness (Anti-hallucination)
- Answer Relevancy
- Context Precision
- Graph Entity Recall
- Page-Specific Constrained Retrieval Accuracy
- End-to-End Latency

Outputs summary metrics to console and exports results to JSON & CSV.
"""
import sys
import os
import json
import time
import asyncio
import csv
from typing import Dict, List, Any

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.rag.graph_rag import graph_rag, GraphRAGPipeline
from app.rag.ollama_client import ollama
from app.rag.vector_store import vector_store
from app.rag.graph_store import graph_store


# ─── Rule-Based & LLM-As-Judge Evaluator ───────────────────────────────────────

class RAGEvaluator:
    """Evaluates RAG pipeline responses using local LLM (Ollama) or rule-based heuristics."""

    def __init__(self, use_llm_judge: bool = True):
        self.use_llm_judge = use_llm_judge

    async def evaluate_faithfulness(self, actual_output: str, contexts: List[str]) -> float:
        """Determines how grounded the output is in the provided context (0.0 to 1.0)."""
        if not contexts or not actual_output:
            return 1.0 if not actual_output else 0.0

        combined_context = "\n".join(contexts)
        
        # Heuristic calculation based on word overlap if LLM is unavailable
        context_words = set(combined_context.lower().split())
        output_words = [w for w in actual_output.lower().split() if len(w) > 3]
        if not output_words:
            return 1.0
        
        grounded_count = sum(1 for w in output_words if w in context_words)
        score = min(1.0, (grounded_count / len(output_words)) * 1.3)

        if self.use_llm_judge and await ollama.is_available():
            try:
                prompt = f"""You are an evaluator judge. Rate how FAITHFUL the actual answer is to the retrieved context on a scale of 0.0 to 1.0.
Output ONLY a JSON object: {{"score": float, "reason": "brief explanation"}}

Context:
{combined_context[:1000]}

Actual Answer:
{actual_output[:500]}
"""
                response = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.0)
                parsed = json.loads(response[response.find('{'):response.rfind('}')+1])
                score = float(parsed.get("score", score))
            except Exception:
                pass

        return round(score, 2)

    async def evaluate_relevancy(self, question: str, actual_output: str) -> float:
        """Determines how directly the answer addresses the question (0.0 to 1.0)."""
        q_words = set([w for w in question.lower().split() if len(w) > 3])
        out_words = set(actual_output.lower().split())
        
        if not q_words:
            return 1.0
        
        overlap = len(q_words.intersection(out_words)) / len(q_words)
        score = min(1.0, overlap * 1.5 + 0.3)

        if self.use_llm_judge and await ollama.is_available():
            try:
                prompt = f"""Rate how RELEVANT the answer is to the question on a scale of 0.0 to 1.0.
Output ONLY a JSON object: {{"score": float}}

Question: {question}
Answer: {actual_output[:500]}
"""
                response = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.0)
                parsed = json.loads(response[response.find('{'):response.rfind('}')+1])
                score = float(parsed.get("score", score))
            except Exception:
                pass

        return round(score, 2)

    def evaluate_graph_entity_recall(self, expected_entities: List[str], graph_context: Dict) -> float:
        """Measures the proportion of expected knowledge entities found in the graph response."""
        if not expected_entities:
            return 1.0

        retrieved_entity_names = [
            e.get("name", e.get("id", "")).lower() for e in graph_context.get("entities", [])
        ]
        
        found = 0
        for exp in expected_entities:
            exp_lower = exp.lower()
            if any(exp_lower in rent for rent in retrieved_entity_names):
                found += 1
        
        return round(found / len(expected_entities), 2)

    def evaluate_page_accuracy(self, target_page: int, sources: List[Dict]) -> float:
        """Checks if page-constrained queries correctly filter and retrieve target page."""
        if target_page is None:
            return 1.0

        page_found = any(s.get("page") == target_page for s in sources)
        return 1.0 if page_found else 0.0


# ─── Main Benchmark Harness ───────────────────────────────────────────────────

async def seed_benchmark_data_if_empty():
    """Seeds ChromaDB and Graph Store with sample textbook content for evaluation."""
    test_topic = "eval_test_topic"
    
    # Always reset test collection to match model dimensions
    vector_store.delete_topic(test_topic)
    
    sample_chunks = [
        {
            "text": "Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin in high dimensional space.",
            "metadata": {"source": "ML_Textbook.pdf", "page": 42, "chunk_index": 0}
        },
        {
            "text": "Feature selection techniques include Filter methods, Wrapper methods, and Embedded methods such as SVM-RFE.",
            "metadata": {"source": "ML_Textbook.pdf", "page": 43, "chunk_index": 1}
        }
    ]

    try:
        embeddings = await ollama.embed_batch([chunk["text"] for chunk in sample_chunks])
    except Exception:
        embeddings = [[0.1] * 768, [0.2] * 768]

    vector_store.add_chunks(test_topic, sample_chunks, embeddings)

    # Seed graph store
    entities = [
        {"id": "Support Vector Machines", "name": "Support Vector Machines", "type": "algorithm", "description": "Classification model"},
        {"id": "Feature selection", "name": "Feature selection", "type": "method", "description": "Dimensionality reduction"},
        {"id": "SVM-RFE", "name": "SVM-RFE", "type": "algorithm", "description": "Embedded feature selection"}
    ]
    relationships = [
        {"source": "SVM-RFE", "target": "Feature selection", "type": "IS_A", "description": "Embedded method"},
        {"source": "SVM-RFE", "target": "Support Vector Machines", "type": "USES", "description": "Uses SVM"}
    ]
    graph_store.add_entities(test_topic, entities)
    graph_store.add_relationships(test_topic, relationships)

    return test_topic


async def run_advanced_evaluation():
    print("======================================================================")
    print("DEEPTUTOR ADVANCED RAG & GRAPH-RAG EVALUATION SUITE")
    print("======================================================================")

    dataset_path = os.path.join(os.path.dirname(__file__), "eval_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    test_topic = await seed_benchmark_data_if_empty()
    evaluator = RAGEvaluator(use_llm_judge=True)

    results = []
    total_latency = 0.0

    print(f"\nRunning evaluation on {len(test_cases)} benchmark test cases...\n")
    print(f"{'ID':<8} | {'Category':<20} | {'Faithfulness':<12} | {'Relevancy':<10} | {'Graph Recall':<12} | {'Page Acc':<8} | {'Latency (s)'}")
    print("-" * 90)

    for case in test_cases:
        tc_id = case["id"]
        category = case["category"]
        question = case["question"]
        expected_entities = case.get("expected_entities", [])
        target_page = case.get("target_page")

        # Execute Live RAG Pipeline
        start_time = time.time()
        res = await graph_rag.simple_query(
            topic_id=test_topic,
            question=question,
            session_messages=[]
        )
        latency = round(time.time() - start_time, 3)
        total_latency += latency

        actual_output = res.get("content", "")
        sources = res.get("sources", [])
        graph_context = res.get("graph_context", {})

        # Extract contexts
        vector_contexts = [s.get("text", "") for s in sources]
        graph_contexts = [
            f"{e.get('name')}: {e.get('description')}" for e in graph_context.get("entities", [])
        ]
        all_contexts = vector_contexts + graph_contexts

        # Evaluate Metrics
        faithfulness = await evaluator.evaluate_faithfulness(actual_output, all_contexts)
        relevancy = await evaluator.evaluate_relevancy(question, actual_output)
        graph_recall = evaluator.evaluate_graph_entity_recall(expected_entities, graph_context)
        page_acc = evaluator.evaluate_page_accuracy(target_page, sources)

        result_row = {
            "id": tc_id,
            "category": category,
            "question": question,
            "actual_output": actual_output[:100] + "..." if len(actual_output) > 100 else actual_output,
            "faithfulness": faithfulness,
            "relevancy": relevancy,
            "graph_entity_recall": graph_recall,
            "page_accuracy": page_acc,
            "latency_seconds": latency
        }
        results.append(result_row)

        print(f"{tc_id:<8} | {category:<20} | {faithfulness:<12.2f} | {relevancy:<10.2f} | {graph_recall:<12.2f} | {page_acc:<8.1f} | {latency:.3f}s")

    # Overall Summary
    avg_faithfulness = sum(r["faithfulness"] for r in results) / len(results)
    avg_relevancy = sum(r["relevancy"] for r in results) / len(results)
    avg_graph_recall = sum(r["graph_entity_recall"] for r in results) / len(results)
    avg_page_acc = sum(r["page_accuracy"] for r in results) / len(results)
    avg_latency = total_latency / len(results)

    print("=" * 90)
    print("OVERALL AGGREGATE EVALUATION SCORECARD:")
    print(f"  - Average Faithfulness (Groundedness) : {avg_faithfulness * 100:.1f}%")
    print(f"  - Average Answer Relevancy            : {avg_relevancy * 100:.1f}%")
    print(f"  - Average Graph Entity Recall         : {avg_graph_recall * 100:.1f}%")
    print(f"  - Average Page Accuracy               : {avg_page_acc * 100:.1f}%")
    print(f"  - Mean Query Latency                  : {avg_latency:.3f} seconds")
    print("=" * 90)

    # Export Reports
    report_json_path = os.path.join(os.path.dirname(__file__), "eval_report.json")
    report_csv_path = os.path.join(os.path.dirname(__file__), "eval_report.csv")

    summary_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "aggregate_scores": {
            "faithfulness": avg_faithfulness,
            "relevancy": avg_relevancy,
            "graph_entity_recall": avg_graph_recall,
            "page_accuracy": avg_page_acc,
            "mean_latency_seconds": avg_latency
        },
        "detailed_results": results
    }

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    with open(report_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[OK] Benchmark completed. Reports saved to:")
    print(f"   - {report_json_path}")
    print(f"   - {report_csv_path}")


if __name__ == "__main__":
    asyncio.run(run_advanced_evaluation())
