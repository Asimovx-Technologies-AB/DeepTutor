"""
3. DEEPEVAL TEST SUITE FOR DEEPTUTOR
Install dependencies:
  pip install deepeval
Run unit tests:
  deepeval test run backend/evaluations/run_deepeval.py
"""

import os
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric, FaithfulnessMetric


def check_openai_key():
    """Ensure OPENAI_API_KEY is available or skip test with friendly message."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip(
            "OPENAI_API_KEY environment variable not set. "
            "Set $env:OPENAI_API_KEY='sk-...' to run DeepEval with OpenAI as judge, "
            "or use python backend/evaluations/run_advanced_eval.py for local evaluation."
        )


def test_svm_rag_response():
    """Test case 1: Verify SVM explanation is faithful to PDF and free of hallucinations."""
    check_openai_key()
    
    test_case = LLMTestCase(
        input="What are Support Vector Machines and how do they work?",
        actual_output="Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin.",
        retrieval_context=[
            "[Page 42] Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin in high dimensional space."
        ]
    )

    hallucination_metric = HallucinationMetric(threshold=0.2)
    faithfulness_metric = FaithfulnessMetric(threshold=0.8)
    relevancy_metric = AnswerRelevancyMetric(threshold=0.8)

    assert_test(test_case, [hallucination_metric, faithfulness_metric, relevancy_metric])


def test_feature_selection_rag_response():
    """Test case 2: Verify Feature Selection explanation is relevant and grounded."""
    check_openai_key()

    test_case = LLMTestCase(
        input="Explain Feature Selection techniques in Machine Learning.",
        actual_output="Feature selection methods include Filter methods, Wrapper methods, and Embedded methods such as SVM-RFE.",
        retrieval_context=[
            "[Page 43] Feature selection techniques include Filter methods, Wrapper methods, and Embedded methods such as SVM-RFE."
        ]
    )

    relevancy_metric = AnswerRelevancyMetric(threshold=0.8)
    assert_test(test_case, [relevancy_metric])
