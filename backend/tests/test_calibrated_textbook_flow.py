import pytest
import uuid
from unittest.mock import patch, AsyncMock
from app.services.study_agents import (
    QueryAnalyzerAgent,
    DecisionAgent,
    parse_learning_level,
    generate_synthetic_textbook,
    LEVEL_PROFILES,
)
from app.services.study_storage import (
    get_session_topics,
    get_session_documents,
    get_all_chunks,
)


def test_parse_learning_level():
    """Verify parsing for numbers, class grades, and keywords across all 4 tiers."""
    # 1. Primary School (Class 1-5)
    assert parse_learning_level("1") == "primary"
    assert parse_learning_level("option 1") == "primary"
    assert parse_learning_level("tier 1") == "primary"
    assert parse_learning_level("class 1") == "primary"
    assert parse_learning_level("class 3") == "primary"
    assert parse_learning_level("class 5") == "primary"
    assert parse_learning_level("4th standard") == "primary"
    assert parse_learning_level("3rd std") == "primary"
    assert parse_learning_level("grade 2") == "primary"
    assert parse_learning_level("primary school") == "primary"
    assert parse_learning_level("kid") == "primary"

    # 2. Middle & High School (Class 6-12)
    assert parse_learning_level("2") == "secondary"
    assert parse_learning_level("option 2") == "secondary"
    assert parse_learning_level("class 6") == "secondary"
    assert parse_learning_level("class 10") == "secondary"
    assert parse_learning_level("class 12") == "secondary"
    assert parse_learning_level("10th grade") == "secondary"
    assert parse_learning_level("high school") == "secondary"
    assert parse_learning_level("middle school") == "secondary"

    # 3. Undergraduate
    assert parse_learning_level("3") == "undergraduate"
    assert parse_learning_level("btech") == "undergraduate"
    assert parse_learning_level("b.tech") == "undergraduate"
    assert parse_learning_level("bsc") == "undergraduate"
    assert parse_learning_level("college") == "undergraduate"
    assert parse_learning_level("undergrad") == "undergraduate"
    assert parse_learning_level("undergraduate") == "undergraduate"

    # 4. Professional / Postgraduate
    assert parse_learning_level("4") == "professional"
    assert parse_learning_level("working professional") == "professional"
    assert parse_learning_level("postgraduate") == "professional"
    assert parse_learning_level("masters") == "professional"
    assert parse_learning_level("phd") == "professional"


@pytest.mark.asyncio
async def test_calibrated_textbook_flow_primary_school():
    """Verify the 3-turn interactive flow calibrating for Primary School (Class 1-5)."""
    planner = QueryAnalyzerAgent()
    executor = DecisionAgent()
    # Use a unique session ID per test run to avoid cross-test data contamination
    session_id = f"test_calibrated_flow_primary_{uuid.uuid4().hex[:8]}"

    # Turn 1: Student specifies subject with no uploaded documents
    plan1 = await planner.plan("Machine Learning", subject="General Study")
    res1 = await executor.execute(
        session_id=session_id,
        user_query="Machine Learning",
        subject="General Study",
        plan=plan1,
        history=[]
    )
    assert "Do you have study material" in res1["response"]
    assert "**Machine Learning**" in res1["response"]

    # Turn 2: Student replies "no"
    history_turn2 = [
        {"role": "user", "text": "Machine Learning"},
        {"role": "assistant", "text": res1["response"]}
    ]
    plan2 = await planner.plan("no", subject="Machine Learning", history=history_turn2)
    res2 = await executor.execute(
        session_id=session_id,
        user_query="no",
        subject="Machine Learning",
        plan=plan2,
        history=history_turn2
    )
    # Verifies the 4-tier level inquiry is presented
    assert "Personalize Your Learning Journey" in res2["response"]
    assert "Primary School (Class 1–5)" in res2["response"]
    assert "Middle & High School (Class 6–12)" in res2["response"]
    assert "Undergraduate (B.Tech / BSc)" in res2["response"]
    assert "Professional / Postgraduate" in res2["response"]

    # Turn 3: Student responds with "1" (Primary School)
    history_turn3 = history_turn2 + [
        {"role": "user", "text": "no"},
        {"role": "assistant", "text": res2["response"]}
    ]
    plan3 = await planner.plan("1", subject="Machine Learning", history=history_turn3)

    mock_llm_json = """
```json
{
  "curriculum": [
    {
      "id": "module_1",
      "title": "Module 1: Meet the Robot Brain!",
      "summary": "A friendly story introducing how computers can learn like smart puppies.",
      "difficulty": "Exploring",
      "key_concepts": ["Robot Friend", "Smart Toys", "Pattern Games"],
      "estimated_study_time": "20-25 mins",
      "real_world_anchor": "Young learners and their favourite toys"
    }
  ]
}
```

# Module 1: Meet the Robot Brain! 🌟

> **Level**: Primary School (Class 1–5)

## § 1 — Chapter Overview
This chapter follows Sparky the robot puppy and how he learns tricks.

## § 2 — Prerequisite Check
1. Do you have a favourite toy that does something smart?

## § 3 — Case Study Hook
Sparky is a toy puppy who learns to sit when you clap your hands!

## § 4 — Core Content
In real life, this looks like... computers learning from many examples.

Imagine you have a friendly puppy named Sparky! Sparky learns new tricks when you give him yummy treats. That is how computers learn too!

## § 5 — Worked Examples
Example 1: Sparky sees 10 cats. He learns cats meow. He sees a new cat — what does he expect?

## § 6 — Interactive Checkpoints
- Can you name one toy you have that makes sounds or plays games? 🎈
- What would happen if Sparky only saw 1 cat? Would he still learn well?
- You are Sparky's trainer — what would you show him to help him learn faster?

## § 7 — Key Terms
| **Word** | **What It Means** |
|---|---|
| Pattern | Something that repeats |
| Learning | Getting better with practice |

## § 8 — Practice Exercises
Tier 1: Name 2 smart toys you know. What do they learn to do?

## § 9 — Real-World Connections
Doctors use computers that learn to spot sick people sooner.

## § 10 — Chapter Summary
We learned that computers (like Sparky!) get smarter when they practice with lots of examples.

## § 11 — Self-Assessment Rubric
| **Can I now...?** | Not Yet | Getting There | Yes! |
|---|---|---|---|
| Explain how Sparky learns | ☐ | ☐ | ☐ |

## § 12 — Answer Key
Tier 1: Answers vary — focus on the idea of feedback and practice.

## § 13 — Try It Yourself!
Teach a family member a new word by repeating it 5 times with examples. Can they use it correctly?
"""

    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_llm_json)):
        res3 = await executor.execute(
            session_id=session_id,
            user_query="1",
            subject="Machine Learning",
            plan=plan3,
            history=history_turn3
        )

    assert res3["is_synthetic_textbook"] is True
    assert res3["level"] == "primary"
    assert "Primary School (Class 1–5)" in res3["level_name"]
    assert "Robot Brain" in res3["response"]
    # New format: checkpoints are embedded under § 6 in the chapter content
    assert "Quick-Start Checkpoints" in res3["response"] or "§ 6" in res3["response"]
    assert "Can you name one toy" in res3["response"]

    # Verify session topics and documents are registered
    topics = get_session_topics(session_id)
    assert len(topics) >= 1
    assert "Robot Brain" in topics[0]["title"]

    chunks = get_all_chunks(session_id)
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_calibrated_textbook_flow_inline_class_shortcut():
    """Verify that saying 'no, I am in 4th standard' directly generates the Primary School textbook in 1 turn."""
    planner = QueryAnalyzerAgent()
    executor = DecisionAgent()
    # Use a unique session ID per test run to avoid cross-test data contamination
    session_id = f"test_calibrated_flow_shortcut_{uuid.uuid4().hex[:8]}"

    history = [
        {"role": "user", "text": "Science"},
        {"role": "assistant", "text": "Do you have study material for **Science**?"}
    ]
    plan = await planner.plan("no, I am in 4th standard", subject="Science", history=history)

    # The new format: LLM returns a ```json ... ``` block followed by markdown chapter text
    mock_llm_response = """
```json
{
  "curriculum": [
    {
      "id": "module_1",
      "title": "Module 1: Wonders of Nature",
      "summary": "Fun discovery about plants and sunlight.",
      "difficulty": "Exploring",
      "key_concepts": ["Plants", "Sunlight"],
      "estimated_study_time": "20-25 mins",
      "real_world_anchor": "Young learners exploring the school garden"
    }
  ]
}
```

# Module 1: Wonders of Nature 🌟

> **Level**: Primary School (Class 1–5)

## § 1 — Chapter Overview
This chapter follows Mia as she discovers plants and sunlight in her garden.

## § 2 — Prerequisite Check
1. Have you seen a plant grow? 🌱

## § 3 — Case Study Hook
Mia waters her plant and watches it grow toward the Sun.

## § 4 — Core Content
In real life, this looks like... plants turning green in sunlight.

## § 5 — Worked Examples
Example 1: Mia counts 3 yellow flowers and 2 red ones.

## § 6 — Interactive Checkpoints
- Look outside: what green plant do you see? 🌿
- Can you name one plant in your home?
- Why do plants need sunlight?

## § 7 — Key Terms
| **Word** | **What It Means** |
|---|---|
| Sunlight | Energy from the Sun |
| Photosynthesis | How plants make food |

## § 8 — Practice Exercises
Tier 1: Name 3 plants you know.

## § 9 — Real-World Connections
Farmers use this every day.

## § 10 — Chapter Summary
We learned that plants need sunlight, water, and soil.

## § 11 — Self-Assessment Rubric
| **Can I now...?** | Not Yet | Getting There | Yes! |
|---|---|---|---|
| Name a plant | ☐ | ☐ | ☐ |

## § 12 — Answer Key
Tier 1: Answers vary.

## § 13 — Try It Yourself!
Water a plant at home and observe for 3 days.
"""
    with patch("app.services.study_agents.call_llm", new=AsyncMock(return_value=mock_llm_response)):
        res = await executor.execute(
            session_id=session_id,
            user_query="no, I am in 4th standard",
            subject="Science",
            plan=plan,
            history=history
        )

    assert res["is_synthetic_textbook"] is True
    assert res["level"] == "primary"
    assert "Primary School (Class 1–5)" in res["level_name"]
    # The chapter title is extracted from the H1 heading in the markdown
    assert "Wonders of Nature" in res["response"] or "Science" in res["response"]
    assert "§ 6" in res["response"] or "Checkpoints" in res["response"]
