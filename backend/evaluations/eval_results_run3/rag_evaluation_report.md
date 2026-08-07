# DeepTutor RAG Evaluation Report
_Generated: 2026-08-07 14:07:13_

## Overall Scorecard

| Metric | Score | Threshold | Result |
|---|---|---|---|
| faithfulness | 64.0% | ≥75% | ❌ FAIL |
| relevancy | 80.0% | ≥70% | ✅ PASS |
| context_precision | 24.0% | ≥60% | ❌ FAIL |
| graph_entity_recall | 39.5% | ≥60% | ❌ FAIL |
| page_accuracy | 100.0% | ≥90% | ✅ PASS |

**Latency** — mean 21.16s, p50 17.383s, p95 35.221s
**Errors:** 0 / 5 test cases

## Cross-Topic Isolation Check

✅ PASS — no cross-topic contamination detected.

## Per-Category Breakdown

### concept_explanation (1 cases)
- faithfulness: 80.0%
- relevancy: 100.0%
- context_precision: 40.0%
- graph_entity_recall: 33.0%

### feature_selection (1 cases)
- faithfulness: 80.0%
- relevancy: 100.0%
- context_precision: 40.0%
- graph_entity_recall: 25.0%

### graph_multihop (1 cases)
- faithfulness: 80.0%
- relevancy: 100.0%
- context_precision: 40.0%
- graph_entity_recall: 100.0%

### out_of_domain (1 cases)
- faithfulness: 0.0%
- relevancy: 0.0%
- context_precision: 0.0%

### page_constrained (1 cases)
- faithfulness: 80.0%
- relevancy: 100.0%
- context_precision: 0.0%
- graph_entity_recall: 0.0%
- page_accuracy: 100.0%
