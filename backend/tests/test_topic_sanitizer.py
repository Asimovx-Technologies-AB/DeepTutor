import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.rag.topic_sanitizer import is_valid_academic_topic, clean_and_format_topic, deduplicate_and_rank_topics


def test_topic_sanitizer_rules():
    # 1. Test Garbage / Table Noise from user's document
    bad_samples = [
        "Tpr Cpp202 Ipir Cpp202 Cpir Cpp202 Fpr Cpp202 Rpr Cpp202",
        "(Tc2022) (C2022)",
        "Results and Discussion",
        "Characteristics of publication outputs",
        "Discussion",
        "Abstract",
        "Introduction",
        "Conclusion",
        "References",
        "Table 1",
        "Figure 2.1",
        "http://example.com",
        "doi:10.1109/5.771073",
        "p. 42",
        "A",
        "AB",
        "(2022)",
        "[14]",
    ]

    for bad in bad_samples:
        valid = is_valid_academic_topic(bad)
        assert not valid, f"Expected '{bad}' to be rejected, but got valid={valid}"
    print("[OK] All bad table/boilerplate samples were correctly rejected!")

    # 2. Test Good Academic Concepts
    good_samples = [
        "Open Research Challenges and Opportunities Relative to Global South Regions",
        "Support Vector Machines",
        "Convolutional Neural Networks",
        "Gradient Descent Optimization",
        "Graph Neural Networks",
        "Feature Selection Techniques",
        "Natural Language Processing",
        "Recurrent Neural Networks"
    ]

    for good in good_samples:
        valid = is_valid_academic_topic(good)
        assert valid, f"Expected '{good}' to be valid, but got rejected"
        clean = clean_and_format_topic(good)
        assert clean is not None
    print("[OK] All real academic concepts were correctly accepted!")

    # 3. Test Deduplication and Ranking
    mixed_input = [
        "Tpr Cpp202 Ipir Cpp202 Cpir Cpp202 Fpr Cpp202 Rpr Cpp202",
        "Results and Discussion",
        "Support Vector Machines",
        "support vector machines",  # duplicate
        "Vector Machines",  # redundant substring
        "(Tc2022) (C2022)",
        "Convolutional Neural Networks",
        "Open Research Challenges and Opportunities Relative to Global South Regions"
    ]

    ranked = deduplicate_and_rank_topics(mixed_input)
    print("Deduplicated output:", ranked)
    assert "Support Vector Machines" in ranked
    assert "Convolutional Neural Networks" in ranked
    assert "Open Research Challenges and Opportunities Relative to Global South Regions" in ranked
    assert "Results and Discussion" not in ranked
    assert "(Tc2022) (C2022)" not in ranked
    assert "Tpr Cpp202 Ipir Cpp202 Cpir Cpp202 Fpr Cpp202 Rpr Cpp202" not in ranked
    print("[OK] Deduplication and filtering passed successfully!")


if __name__ == "__main__":
    test_topic_sanitizer_rules()
    print("\n[ALL TESTS PASSED] Topic sanitizer works flawlessly!")
