"""
1. RAGAS EVALUATION SCRIPT FOR DEEPTUTOR
Install dependencies:
  pip install ragas datasets langchain-community
Run:
  python evaluations/run_ragas_eval.py
"""

import os
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)

# 1. Prepare Ground Truth Evaluation Dataset
eval_data = {
    "question": [
        "What are Support Vector Machines and how do they work?",
        "Explain Feature Selection techniques in Machine Learning.",
        "What is Reinforcement Learning from Human Feedback (RLHF)?"
    ],
    "contexts": [
        ["[Page 42] Support Vector Machines (SVM) find the optimal hyper-plane for separating classes with maximum margin in high dimensional space."],
        ["[Page 43] Feature selection techniques include Filter methods, Wrapper methods, and Embedded methods such as SVM-RFE."],
        ["[Page 1] RLHF is a reinforcement learning method that uses human preferences as a reward signal to align Large Language Models."]
    ],
    "answer": [
        "Support Vector Machines (SVM) are classification algorithms that identify the optimal hyper-plane to separate data classes with the maximum margin.",
        "Feature selection methods are categorized into Filter methods, Wrapper methods, and Embedded methods like SVM-RFE to reduce dataset dimensionality.",
        "RLHF (Reinforcement Learning from Human Feedback) uses human feedback signals to fine-tune and align Large Language Models to human preferences."
    ],
    "ground_truth": [
        "SVM finds hyper-planes for class separation with max margin.",
        "Feature selection includes Filter, Wrapper, and Embedded methods.",
        "RLHF trains models using human feedback rewards."
    ]
}


def run_ragas():
    print("=" * 60)
    print("🚀 RUNNING RAGAS EVALUATION FOR DEEPTUTOR")
    print("=" * 60)

    # Convert dictionary to HuggingFace Dataset
    dataset = Dataset.from_dict(eval_data)

    # Evaluate RAG Triad Metrics
    results = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )

    print("\n📊 RAGAS EVALUATION SCORES:")
    print(results)

    # Convert results to Pandas DataFrame
    df = results.to_pandas()
    df.to_csv("ragas_evaluation_results.csv", index=False)
    print("\n✅ Results saved to 'ragas_evaluation_results.csv'")


if __name__ == "__main__":
    run_ragas()
