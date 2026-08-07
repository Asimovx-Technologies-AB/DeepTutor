"""
Advanced RAG & GraphRAG Evaluation Suite for DeepTutor
------------------------------------------------------
Evaluates the live GraphRAGPipeline on:
  - Faithfulness / Groundedness (anti-hallucination)
  - Answer Relevancy
  - Context Precision            <-- was promised, never implemented; added
  - Graph Entity Recall
  - Page-Specific Constrained Retrieval Accuracy
  - Cross-Topic Isolation        <-- new: catches the "wrong section's data
                                       leaked into this answer" class of bug
  - End-to-End Latency (mean + p50/p95)

Design principles carried over from hardening quiz_generator.py:
  - Never silently substitute fake data (no dummy embeddings on failure —
    abort loudly instead).
  - Never let one bad test case or one bad judge call kill the whole run.
  - Every failure is logged with enough context to diagnose without
    re-running.
  - Pass/fail thresholds + non-zero exit code so this can run in CI.

Outputs: console table, JSON, CSV, and a Markdown summary report.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
# If this script sits directly in the backend/ root rather than a
# subdirectory (matching the original script's layout), also try the
# script's own directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.rag.graph_rag import graph_rag  # noqa: E402
from app.rag.ollama_client import ollama  # noqa: E402
from app.rag.vector_store import vector_store  # noqa: E402
from app.rag.graph_store import graph_store  # noqa: E402

logger = logging.getLogger("deeptutor.eval")


# ─── Data models ────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    id: str
    category: str
    question: str
    expected_entities: List[str] = field(default_factory=list)
    target_page: Optional[int] = None

    @staticmethod
    def from_dict(d: dict) -> "TestCase":
        missing = [k for k in ("id", "category", "question") if k not in d]
        if missing:
            raise ValueError(f"Test case missing required field(s) {missing}: {d!r}")
        return TestCase(
            id=d["id"],
            category=d["category"],
            question=d["question"],
            expected_entities=d.get("expected_entities", []),
            target_page=d.get("target_page"),
        )


@dataclass
class EvalResult:
    id: str
    category: str
    question: str
    actual_output: str
    faithfulness: Optional[float] = None
    relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    graph_entity_recall: Optional[float] = None
    page_accuracy: Optional[float] = None
    latency_seconds: Optional[float] = None
    error: Optional[str] = None

    def scored_metrics(self) -> Dict[str, float]:
        """Only the numeric metrics that actually got computed (error cases excluded)."""
        keys = ["faithfulness", "relevancy", "context_precision", "graph_entity_recall", "page_accuracy"]
        return {k: getattr(self, k) for k in keys if getattr(self, k) is not None}


# ─── Robust JSON extraction from LLM judge output ──────────────────────────

def extract_json_object(text: str) -> Optional[dict]:
    """
    Locate and parse the first balanced {...} object in text. More robust
    than str.find/rfind (which breaks on nested braces or extra prose
    before/after the JSON) and than a bare regex (which breaks on
    truncated output). Returns None rather than raising.
    """
    if not text:
        return None
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        start = None  # keep scanning for another candidate
                        continue
    return None


async def judge_score(prompt: str, retries: int = 1) -> Optional[dict]:
    """Call the local Ollama judge with retry + robust parsing. Returns None on total failure."""
    for attempt in range(retries + 1):
        try:
            response = await ollama.chat([{"role": "user", "content": prompt}], temperature=0.0)
        except Exception as e:
            logger.warning("Judge call failed (attempt %d): %s", attempt + 1, e)
            continue

        parsed = extract_json_object(response)
        if parsed is not None:
            return parsed
        logger.warning(
            "Judge response wasn't valid JSON (attempt %d). Raw (first 300 chars): %r",
            attempt + 1, response[:300],
        )
    return None


# ─── Evaluator ──────────────────────────────────────────────────────────────

class RAGEvaluator:
    """Evaluates RAG pipeline responses using local LLM (Ollama) or rule-based heuristics."""

    def __init__(self, use_llm_judge: bool = True):
        self.use_llm_judge = use_llm_judge

    @staticmethod
    def _heuristic_faithfulness(actual_output: str, combined_context: str) -> float:
        if not actual_output:
            return 1.0
        context_words = set(combined_context.lower().split())
        output_words = [w for w in actual_output.lower().split() if len(w) > 3]
        if not output_words:
            return 1.0
        grounded = sum(1 for w in output_words if w in context_words)
        return round(min(1.0, (grounded / len(output_words)) * 1.3), 2)

    @staticmethod
    def _heuristic_relevancy(question: str, actual_output: str) -> float:
        q_words = {w for w in question.lower().split() if len(w) > 3}
        if not q_words:
            return 1.0
        out_words = set(actual_output.lower().split())
        overlap = len(q_words & out_words) / len(q_words)
        return round(min(1.0, overlap * 1.5 + 0.3), 2)

    async def evaluate_faithfulness(self, actual_output: str, contexts: List[str]) -> float:
        """How grounded the output is in retrieved context (0.0-1.0)."""
        if not actual_output:
            return 0.0
        if not contexts:
            return 0.0  # an ungrounded answer with zero context is NOT trivially faithful

        combined_context = "\n".join(contexts)
        score = self._heuristic_faithfulness(actual_output, combined_context)

        if self.use_llm_judge:
            prompt = (
                "You are an evaluator judge. Rate how FAITHFUL the actual answer is to the "
                "retrieved context on a scale of 0.0 to 1.0. An answer is faithful only if "
                "every claim in it is supported by the context — penalize any unsupported claim.\n"
                'Output ONLY a JSON object: {"score": float, "reason": "brief explanation"}\n\n'
                f"Context:\n{combined_context[:1000]}\n\n"
                f"Actual Answer:\n{actual_output[:500]}\n"
            )
            parsed = await judge_score(prompt)
            if parsed and "score" in parsed:
                try:
                    score = float(parsed["score"])
                except (TypeError, ValueError):
                    logger.warning("Judge returned non-numeric faithfulness score: %r", parsed)

        return round(max(0.0, min(1.0, score)), 2)

    async def evaluate_relevancy(self, question: str, actual_output: str) -> float:
        """How directly the answer addresses the question (0.0-1.0)."""
        if not actual_output:
            return 0.0
        score = self._heuristic_relevancy(question, actual_output)

        if self.use_llm_judge:
            prompt = (
                "Rate how RELEVANT the answer is to the question on a scale of 0.0 to 1.0.\n"
                'Output ONLY a JSON object: {"score": float}\n\n'
                f"Question: {question}\nAnswer: {actual_output[:500]}\n"
            )
            parsed = await judge_score(prompt)
            if parsed and "score" in parsed:
                try:
                    score = float(parsed["score"])
                except (TypeError, ValueError):
                    logger.warning("Judge returned non-numeric relevancy score: %r", parsed)

        return round(max(0.0, min(1.0, score)), 2)

    async def evaluate_context_precision(self, question: str, contexts: List[str]) -> float:
        """
        Of the chunks actually retrieved, what fraction are relevant to the
        question? This was named in the module docstring of the previous
        version but never implemented — added here. Judges each chunk
        independently rather than the batch, since a single combined-judge
        call tends to rubber-stamp everything as relevant.
        """
        if not contexts:
            return 0.0
        if not self.use_llm_judge:
            # Heuristic fallback: keyword overlap between question and chunk.
            q_words = {w for w in question.lower().split() if len(w) > 3}
            if not q_words:
                return 1.0
            relevant = 0
            for c in contexts:
                c_words = set(c.lower().split())
                if q_words & c_words:
                    relevant += 1
            return round(relevant / len(contexts), 2)

        relevant = 0
        judged = 0
        for chunk in contexts[:8]:  # cap judge calls per test case for speed
            prompt = (
                "Does the following CONTEXT CHUNK contain information relevant to "
                "answering the QUESTION? Answer with ONLY a JSON object: "
                '{"relevant": true} or {"relevant": false}\n\n'
                f"QUESTION: {question}\n\nCONTEXT CHUNK:\n{chunk[:500]}\n"
            )
            parsed = await judge_score(prompt)
            judged += 1
            if parsed and parsed.get("relevant") is True:
                relevant += 1
        if judged == 0:
            return 0.0
        return round(relevant / judged, 2)

    @staticmethod
    def evaluate_graph_entity_recall(expected_entities: List[str], graph_context: Dict) -> Optional[float]:
        """Fraction of expected entities found in the graph response. None if not applicable."""
        if not expected_entities:
            return None
        retrieved = [
            e.get("name", e.get("id", "")).lower() for e in graph_context.get("entities", [])
        ]
        found = sum(1 for exp in expected_entities if any(exp.lower() in r for r in retrieved))
        return round(found / len(expected_entities), 2)

    @staticmethod
    def evaluate_page_accuracy(target_page: Optional[int], sources: List[Dict]) -> Optional[float]:
        """Whether a page-constrained query correctly retrieved the target page. None if not applicable."""
        if target_page is None:
            return None
        return 1.0 if any(s.get("page") == target_page for s in sources) else 0.0


# ─── Cross-topic isolation check ───────────────────────────────────────────

async def check_topic_isolation(topic_a: str, topic_b_marker_text: str) -> Dict[str, Any]:
    """
    Seeds a SECOND, distinct topic with clearly identifiable marker content,
    then queries topic_a and verifies none of topic_b's marker content leaks
    into topic_a's retrieved sources. This is the automated regression test
    for the exact bug class this project hit in production (wrong-section
    content appearing in quizzes/chat).
    """
    topic_b = f"{topic_a}__isolation_control"
    vector_store.delete_topic(topic_b)

    marker_chunk = {
        "text": topic_b_marker_text,
        "metadata": {"source": "isolation_control.pdf", "page": 1, "chunk_index": 0},
    }
    try:
        embeddings = await ollama.embed_batch([marker_chunk["text"]])
    except Exception as e:
        logger.error("Isolation check aborted: could not embed control content: %s", e)
        return {"ran": False, "reason": str(e)}

    vector_store.add_chunks(topic_b, [marker_chunk], embeddings)

    probe_question = "Tell me everything you know, covering all available material."
    res = await graph_rag.simple_query(topic_id=topic_a, question=probe_question, session_messages=[])
    sources = res.get("sources", [])
    contamination = [
        s for s in sources
        if topic_b_marker_text.split(":")[0].lower() in str(s.get("text", "")).lower()
    ]

    vector_store.delete_topic(topic_b)

    return {
        "ran": True,
        "contaminated": len(contamination) > 0,
        "contaminating_sources": contamination,
    }


# ─── Benchmark seeding ──────────────────────────────────────────────────────

async def seed_synthetic_benchmark(topic_id: str) -> None:
    """Seeds ChromaDB and the graph store with fixed sample content for a synthetic eval run."""
    vector_store.delete_topic(topic_id)

    sample_chunks = [
        {
            "text": "Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin in high dimensional space.",
            "metadata": {"source": "ML_Textbook.pdf", "page": 42, "chunk_index": 0},
        },
        {
            "text": "Feature selection techniques include Filter methods, Wrapper methods, and Embedded methods such as SVM-RFE.",
            "metadata": {"source": "ML_Textbook.pdf", "page": 43, "chunk_index": 1},
        },
    ]

    try:
        embeddings = await ollama.embed_batch([c["text"] for c in sample_chunks])
    except Exception as e:
        # Do NOT fall back to fake embeddings — a "successful" eval run built
        # on garbage vectors is worse than no run at all, since it produces
        # confident-looking numbers that mean nothing.
        raise RuntimeError(f"Embedding the seed benchmark failed: {e}") from e

    vector_store.add_chunks(topic_id, sample_chunks, embeddings)

    entities = [
        {"id": "Support Vector Machines", "name": "Support Vector Machines", "type": "algorithm", "description": "Classification model"},
        {"id": "Feature selection", "name": "Feature selection", "type": "method", "description": "Dimensionality reduction"},
        {"id": "SVM-RFE", "name": "SVM-RFE", "type": "algorithm", "description": "Embedded feature selection"},
    ]
    relationships = [
        {"source": "SVM-RFE", "target": "Feature selection", "type": "IS_A", "description": "Embedded method"},
        {"source": "SVM-RFE", "target": "Support Vector Machines", "type": "USES", "description": "Uses SVM"},
    ]
    graph_store.add_entities(topic_id, entities)
    graph_store.add_relationships(topic_id, relationships)


# ─── Main harness ───────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "faithfulness": 0.75,
    "relevancy": 0.70,
    "context_precision": 0.60,
    "graph_entity_recall": 0.60,
    "page_accuracy": 0.90,
}


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


async def run_case(
    case: TestCase, topic_id: str, evaluator: RAGEvaluator, semaphore: asyncio.Semaphore
) -> EvalResult:
    async with semaphore:
        start = time.time()
        try:
            res = await graph_rag.simple_query(topic_id=topic_id, question=case.question, session_messages=[])
        except Exception as e:
            logger.error("Pipeline call failed for test case %s: %s", case.id, e)
            return EvalResult(
                id=case.id, category=case.category, question=case.question,
                actual_output="", error=str(e),
            )
        latency = round(time.time() - start, 3)

        actual_output = res.get("content", "")
        sources = res.get("sources", [])
        graph_context = res.get("graph_context", {})
        vector_contexts = [s.get("text", "") for s in sources]
        graph_contexts = [f"{e.get('name')}: {e.get('description')}" for e in graph_context.get("entities", [])]
        all_contexts = vector_contexts + graph_contexts

        try:
            faithfulness = await evaluator.evaluate_faithfulness(actual_output, all_contexts)
            relevancy = await evaluator.evaluate_relevancy(case.question, actual_output)
            context_precision = await evaluator.evaluate_context_precision(case.question, all_contexts)
            graph_recall = evaluator.evaluate_graph_entity_recall(case.expected_entities, graph_context)
            page_acc = evaluator.evaluate_page_accuracy(case.target_page, sources)
        except Exception as e:
            logger.error("Scoring failed for test case %s: %s", case.id, e)
            return EvalResult(
                id=case.id, category=case.category, question=case.question,
                actual_output=actual_output, latency_seconds=latency, error=f"scoring_failed: {e}",
            )

        return EvalResult(
            id=case.id,
            category=case.category,
            question=case.question,
            actual_output=(actual_output[:100] + "...") if len(actual_output) > 100 else actual_output,
            faithfulness=faithfulness,
            relevancy=relevancy,
            context_precision=context_precision,
            graph_entity_recall=graph_recall,
            page_accuracy=page_acc,
            latency_seconds=latency,
        )


def aggregate(results: List[EvalResult]) -> Dict[str, float]:
    metric_names = ["faithfulness", "relevancy", "context_precision", "graph_entity_recall", "page_accuracy"]
    out = {}
    for m in metric_names:
        vals = [getattr(r, m) for r in results if getattr(r, m) is not None and r.error is None]
        out[m] = round(statistics.mean(vals), 4) if vals else None
    latencies = [r.latency_seconds for r in results if r.latency_seconds is not None]
    out["mean_latency_seconds"] = round(statistics.mean(latencies), 3) if latencies else None
    out["p50_latency_seconds"] = round(percentile(latencies, 0.50), 3) if latencies else None
    out["p95_latency_seconds"] = round(percentile(latencies, 0.95), 3) if latencies else None
    out["error_count"] = sum(1 for r in results if r.error is not None)
    out["total_cases"] = len(results)
    return out


def check_pass_fail(overall: Dict[str, float], thresholds: Dict[str, float]) -> Dict[str, bool]:
    verdict = {}
    for metric, threshold in thresholds.items():
        value = overall.get(metric)
        verdict[metric] = (value is not None) and (value >= threshold)
    return verdict


def write_reports(output_dir: Path, summary: dict, results: List[EvalResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "eval_report.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    rows = [asdict(r) for r in results]
    if rows:
        with open(output_dir / "eval_report.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    md_lines = [
        "# DeepTutor RAG Evaluation Report",
        f"_Generated: {summary['timestamp']}_",
        "",
        "## Overall Scorecard",
        "",
        "| Metric | Score | Threshold | Result |",
        "|---|---|---|---|",
    ]
    for metric, threshold in DEFAULT_THRESHOLDS.items():
        value = summary["aggregate_scores"].get(metric)
        passed = summary["pass_fail"].get(metric)
        value_str = f"{value * 100:.1f}%" if value is not None else "N/A"
        result_str = "✅ PASS" if passed else "❌ FAIL"
        md_lines.append(f"| {metric} | {value_str} | ≥{threshold * 100:.0f}% | {result_str} |")

    md_lines += [
        "",
        f"**Latency** — mean {summary['aggregate_scores'].get('mean_latency_seconds')}s, "
        f"p50 {summary['aggregate_scores'].get('p50_latency_seconds')}s, "
        f"p95 {summary['aggregate_scores'].get('p95_latency_seconds')}s",
        f"**Errors:** {summary['aggregate_scores'].get('error_count')} / {summary['aggregate_scores'].get('total_cases')} test cases",
        "",
        "## Cross-Topic Isolation Check",
        "",
    ]
    isolation = summary.get("isolation_check", {})
    if not isolation.get("ran"):
        md_lines.append(f"⚠️ Isolation check did not run: {isolation.get('reason', 'unknown')}")
    elif isolation.get("contaminated"):
        md_lines.append(
            "❌ **FAIL — cross-topic contamination detected.** Retrieved sources for the "
            "test topic included content seeded under a separate control topic. This is the "
            "same class of bug that previously caused off-topic quiz questions — investigate "
            "collection-key scoping immediately."
        )
    else:
        md_lines.append("✅ PASS — no cross-topic contamination detected.")

    md_lines += ["", "## Per-Category Breakdown", ""]
    categories = sorted({r.category for r in results})
    for cat in categories:
        cat_results = [r for r in results if r.category == cat]
        cat_agg = aggregate(cat_results)
        md_lines.append(f"### {cat} ({len(cat_results)} cases)")
        for metric in ["faithfulness", "relevancy", "context_precision", "graph_entity_recall", "page_accuracy"]:
            v = cat_agg.get(metric)
            if v is not None:
                md_lines.append(f"- {metric}: {v * 100:.1f}%")
        md_lines.append("")

    with open(output_dir / "rag_evaluation_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))


async def run_advanced_evaluation(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    print("=" * 70)
    print("DEEPTUTOR ADVANCED RAG & GRAPH-RAG EVALUATION SUITE")
    print("=" * 70)

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        logger.error("Dataset not found: %s", dataset_path)
        return 2

    with open(dataset_path, "r", encoding="utf-8") as f:
        raw_cases = json.load(f)

    if not raw_cases:
        logger.error("Dataset at %s is empty — nothing to evaluate.", dataset_path)
        return 2

    try:
        test_cases = [TestCase.from_dict(c) for c in raw_cases]
    except ValueError as e:
        logger.error("Invalid test case in dataset: %s", e)
        return 2

    topic_id = args.topic_id or "eval_test_topic"
    if not args.real_data:
        try:
            await seed_synthetic_benchmark(topic_id)
        except RuntimeError as e:
            logger.error("Seeding failed, aborting run rather than evaluating against garbage data: %s", e)
            return 2

    evaluator = RAGEvaluator(use_llm_judge=not args.no_llm_judge)
    semaphore = asyncio.Semaphore(args.concurrency)

    print(f"\nRunning {len(test_cases)} test case(s) against topic '{topic_id}' "
          f"(concurrency={args.concurrency}, llm_judge={not args.no_llm_judge})...\n")

    tasks = [run_case(c, topic_id, evaluator, semaphore) for c in test_cases]
    results = await asyncio.gather(*tasks)

    header = f"{'ID':<8} | {'Category':<18} | {'Faith':<6} | {'Relev':<6} | {'CtxPrec':<8} | {'GraphR':<7} | {'PageAcc':<8} | {'Lat(s)':<7} | Error"
    print(header)
    print("-" * len(header))
    for r in results:
        def fmt(v):
            return f"{v:.2f}" if v is not None else "  -  "
        print(
            f"{r.id:<8} | {r.category:<18} | {fmt(r.faithfulness):<6} | {fmt(r.relevancy):<6} | "
            f"{fmt(r.context_precision):<8} | {fmt(r.graph_entity_recall):<7} | {fmt(r.page_accuracy):<8} | "
            f"{r.latency_seconds if r.latency_seconds is not None else '-':<7} | {r.error or ''}"
        )

    isolation_result: Dict[str, Any] = {"ran": False, "reason": "skipped (--no-isolation-check)"}
    if not args.no_isolation_check and not args.real_data:
        isolation_result = await check_topic_isolation(
            topic_id, "CONTROL_MARKER: The secret capital of Wakanda is Birnin Zana."
        )

    overall = aggregate(list(results))
    pass_fail = check_pass_fail(overall, args.thresholds_dict)
    if isolation_result.get("ran") and isolation_result.get("contaminated"):
        pass_fail["cross_topic_isolation"] = False
    elif isolation_result.get("ran"):
        pass_fail["cross_topic_isolation"] = True

    print("\n" + "=" * 70)
    print("OVERALL AGGREGATE SCORECARD")
    for metric in ["faithfulness", "relevancy", "context_precision", "graph_entity_recall", "page_accuracy"]:
        v = overall.get(metric)
        status = "PASS" if pass_fail.get(metric) else "FAIL"
        print(f"  - {metric:<22}: {f'{v * 100:.1f}%' if v is not None else 'N/A':<8} [{status}]")
    print(f"  - mean latency         : {overall.get('mean_latency_seconds')}s "
          f"(p50 {overall.get('p50_latency_seconds')}s, p95 {overall.get('p95_latency_seconds')}s)")
    print(f"  - errors               : {overall.get('error_count')}/{overall.get('total_cases')}")
    if isolation_result.get("ran"):
        print(f"  - cross-topic isolation: {'FAIL — CONTAMINATED' if isolation_result.get('contaminated') else 'PASS'}")
    print("=" * 70)

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "topic_id": topic_id,
        "aggregate_scores": overall,
        "pass_fail": pass_fail,
        "isolation_check": isolation_result,
        "detailed_results": [asdict(r) for r in results],
    }

    output_dir = Path(args.output_dir)
    write_reports(output_dir, summary, list(results))
    print(f"\nReports written to: {output_dir.resolve()}")

    overall_pass = all(pass_fail.values()) if pass_fail else False
    return 0 if overall_pass else 1


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepTutor advanced RAG/GraphRAG evaluation suite")
    parser.add_argument("--dataset", default=str(Path(__file__).parent / "eval_dataset.json"),
                         help="Path to eval_dataset.json")
    parser.add_argument("--output-dir", default=str(Path(__file__).parent),
                         help="Directory to write eval_report.json/.csv/.md")
    parser.add_argument("--topic-id", default=None,
                         help="Evaluate against this existing topic/section instead of the synthetic seed")
    parser.add_argument("--real-data", action="store_true",
                         help="Skip synthetic seeding and isolation control seeding; evaluate --topic-id as-is")
    parser.add_argument("--no-llm-judge", action="store_true",
                         help="Use heuristic scoring only, skip Ollama judge calls (faster, less accurate)")
    parser.add_argument("--no-isolation-check", action="store_true",
                         help="Skip the cross-topic contamination check")
    parser.add_argument("--concurrency", type=int, default=1,
                         help="Max concurrent pipeline calls (keep at 1 for a single local Ollama instance)")
    parser.add_argument("--verbose", action="store_true", help="Debug-level logging")
    for metric, default in DEFAULT_THRESHOLDS.items():
        parser.add_argument(f"--threshold-{metric.replace('_', '-')}", type=float, default=default)

    args = parser.parse_args(argv)
    args.thresholds_dict = {
        metric: getattr(args, f"threshold_{metric}") for metric in DEFAULT_THRESHOLDS
    }
    return args


if __name__ == "__main__":
    exit_code = asyncio.run(run_advanced_evaluation(parse_args()))
    sys.exit(exit_code)