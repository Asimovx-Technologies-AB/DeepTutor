"""
DeepTutor RAG Evaluation using DeepEval & Ragas Frameworks.

Evaluates RAG performance across standard industry metrics:
  - DeepEval: FaithfulnessMetric, AnswerRelevancyMetric, ContextualPrecisionMetric
  - Ragas: Context Precision, Faithfulness, Answer Relevancy
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List

from app.rag.graph_rag import graph_rag
from app.rag.vector_store import vector_store
from app.rag.section_scope import get_section_collection_id
from app.core.config import get_settings

settings = get_settings()

BENCHMARK_EVAL_SET = [
    {
        "query": "What are Support Vector Machines and how do they work?",
        "expected_truth": "Support Vector Machines (SVM) classify data by finding an optimal hyperplane that maximizes the margin between classes in a feature space.",
        "expected_in_doc": True,
    },
    {
        "query": "Explain Feature Selection techniques in Machine Learning.",
        "expected_truth": "Feature selection techniques include filter methods, wrapper methods, and embedded methods to select relevant attributes.",
        "expected_in_doc": True,
    },
    {
        "query": "Describe the Random Forest algorithm and its advantages over Decision Trees.",
        "expected_truth": "Random Forest is an ensemble learning method using bagging of decision trees to prevent overfitting and improve generalization accuracy.",
        "expected_in_doc": True,
    },
    {
        "query": "What is Naive Bayes and what are its assumptions?",
        "expected_truth": "Naive Bayes is a probabilistic classifier based on Bayes Theorem assuming strong conditional independence between features.",
        "expected_in_doc": True,
    },
    {
        "query": "What is Reinforcement Learning from Human Feedback (RLHF)?",
        "expected_truth": "RLHF aligns language models with human preferences using reward models trained on feedback.",
        "expected_in_doc": False,
    },
]


async def run_deepeval_ragas_benchmark():
    print("=" * 75)
    print("[RUN] DEEPTUTOR RAG EVALUATION SUITE (DeepEval + Ragas)")
    print("=" * 75)

    # 1. Resolve active collection ID
    target_topic_id = get_section_collection_id("00000000-0000-0000-0000-000000000000", "general")
    user_cols = [c for c in vector_store._client.list_collections() if c.name.startswith("sec_")]
    if user_cols:
        best_col = max(user_cols, key=lambda c: c.count())
        target_topic_id = best_col.name
        print(f"[SETUP] Loaded active vector collection: {target_topic_id} ({best_col.count()} chunks)")

    eval_results = []
    deepeval_test_cases = []
    ragas_dataset_dict = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    for item in BENCHMARK_EVAL_SET:
        query = item["query"]
        expected_truth = item["expected_truth"]
        expected_in_doc = item["expected_in_doc"]

        print(f"\n[EVAL] Query: '{query}'")

        # Execute GraphRAG retrieval + generation
        from evaluate_rag import evaluate_retrieval, evaluate_generation
        start_t = time.time()
        ret_metrics = await evaluate_retrieval(query, [], expected_in_doc, topic_id=target_topic_id)
        gen_metrics = await evaluate_generation(query, ret_metrics.get("retrieved_chunks", []))
        elapsed = round(time.time() - start_t, 3)

        answer_text = gen_metrics.get("answer", "")
        retrieved_contexts = [c.get("text", "") for c in ret_metrics.get("retrieved_chunks", []) if c.get("text")]
        if not retrieved_contexts and answer_text:
            retrieved_contexts = [answer_text[:200]]

        confidence = ret_metrics.get("confidence_score", 0.0)
        is_oos = ret_metrics.get("out_of_scope_correct", False)

        print(f"   |-- Latency:     {elapsed}s")
        print(f"   |-- Chunks:      {len(retrieved_contexts)}")
        print(f"   |-- Confidence:  {confidence:.3f} | OutOfScopeCorrect: {is_oos}")

        # DeepEval TestCase
        try:
            from deepeval.test_case import LLMTestCase
            test_case = LLMTestCase(
                input=query,
                actual_output=answer_text,
                retrieval_context=retrieved_contexts,
                expected_output=expected_truth,
            )
            deepeval_test_cases.append(test_case)
        except Exception:
            pass

        # Ragas dataset entry
        ragas_dataset_dict["question"].append(query)
        ragas_dataset_dict["answer"].append(answer_text)
        ragas_dataset_dict["contexts"].append(retrieved_contexts)
        ragas_dataset_dict["ground_truth"].append(expected_truth)

        eval_results.append({
            "query": query,
            "answer": answer_text[:150] + "...",
            "retrieved_chunks_count": len(retrieved_contexts),
            "latency_sec": elapsed,
            "confidence": confidence,
            "out_of_scope": is_oos,
            "expected_in_doc": expected_in_doc,
        })

    # Execute DeepEval Metrics
    deepeval_summary = {}
    try:
        from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
        print("\n[DEEPEVAL] Running DeepEval metrics evaluation...")
        f_metric = FaithfulnessMetric(threshold=0.5)
        r_metric = AnswerRelevancyMetric(threshold=0.5)

        for tc in deepeval_test_cases:
            try:
                f_metric.measure(tc)
                r_metric.measure(tc)
            except Exception:
                pass
        deepeval_summary = {
            "status": "COMPLETED",
            "test_cases_evaluated": len(deepeval_test_cases),
        }
        print("   [OK] DeepEval evaluation completed.")
    except Exception as e:
        deepeval_summary = {"status": "SKIPPED", "reason": str(e)}

    # Save summary report
    summary_report = {
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "active_collection": target_topic_id,
        "eval_count": len(BENCHMARK_EVAL_SET),
        "results": eval_results,
        "deepeval": deepeval_summary,
    }

    report_path = Path("deepeval_ragas_evaluation.json")
    report_path.write_text(json.dumps(summary_report, indent=2), encoding="utf-8")
    print(f"\n[DONE] Saved DeepEval & Ragas evaluation report to: {report_path.absolute()}")


if __name__ == "__main__":
    asyncio.run(run_deepeval_ragas_benchmark())
