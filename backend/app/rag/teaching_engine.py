"""
Teaching Engine for Normal Mode and Teacher Mode.
Normal Mode: Step-by-step progressive core idea breakdown (Big Picture -> Core Principle -> Key Takeaways -> Common Pitfalls) + interactive doubt clarification.
Teacher Mode: Introduction -> Simple Explanation -> Deep Breakdown -> Comprehensive Exam.
All responses are formatted professionally with clean mathematics and strictly zero emojis.
"""
import json
import re
import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Any
from app.rag.ollama_client import ollama

NORMAL_CORE_IDEA_PROMPT = """You are an elite academic tutor. The student is exploring the topic: "{topic_title}".
Context summary: {topic_summary}

MATERIAL CONTEXT:
{context}

Provide a structured, step-by-step, pedagogical breakdown of the CORE IDEA for "{topic_title}".

FORMATTING RULES:
- Write clean, human-readable mathematics (e.g., use "ŷ = w·x + b", "σ(z) = 1 / (1 + e⁻ᶻ)", "Loss = (1/n) · Σ(y - ŷ)²").
- DO NOT output unrendered raw LaTeX markup with complex dollar signs.
- DO NOT use any emojis. Maintain an articulate, professional academic tone.
- Format variable definitions and mechanisms with clean bullet points.

Return strictly valid JSON with this exact 4-step structure:
{{
  "steps": [
    {{
      "step_id": "big_picture",
      "step_number": 1,
      "tag": "THE BIG PICTURE",
      "title": "The Big Picture",
      "subtitle": "High-level intuition and fundamental purpose",
      "content": "2-3 clear, impactful sentences explaining what this concept is, why it was invented, and the high-level intuition."
    }},
    {{
      "step_id": "core_principle",
      "step_number": 2,
      "tag": "CORE PRINCIPLE",
      "title": "Core Principle and Mechanics",
      "subtitle": "The governing rules, algorithms, or mathematical formulation",
      "content": "Clear breakdown of the primary mechanism, governing formulas (in clean readable format), and step-by-step execution."
    }},
    {{
      "step_id": "key_takeaways",
      "step_number": 3,
      "tag": "KEY TAKEAWAYS",
      "title": "Key Takeaways and Core Insights",
      "subtitle": "High-yield takeaways to remember",
      "content": "- **Point 1**: Core insight.\n- **Point 2**: Practical application.\n- **Point 3**: Critical rule."
    }},
    {{
      "step_id": "common_pitfall",
      "step_number": 4,
      "tag": "COMMON PITFALL",
      "title": "Common Pitfalls and Exam Traps",
      "subtitle": "Frequent student misconceptions and mistakes",
      "content": "Detailed explanation of what students typically get wrong about this concept on exams, and how to avoid the trap."
    }}
  ]
}}

JSON OUTPUT ONLY:"""

TEACHER_MODE_PROMPT = """You are an engaging, world-class university professor teaching "{topic_title}".
Your student wants to master this topic from scratch.

MATERIAL CONTEXT:
{context}

CRITICAL FORMATTING GUIDELINES:
1. Write clean, readable mathematics (e.g. use "ŷ = w·x + b", "σ(z) = 1 / (1 + e⁻ᶻ)", "MSE = (1/n) · Σ(y - ŷ)²"). DO NOT output raw LaTeX markup.
2. DO NOT use any emojis in your response. Maintain an articulate, professional academic tone.
3. Structure multi-part topics with clear subheadings (e.g. "### Part A: Linear Regression" and "### Part B: Logistic Regression").
4. Format variable definitions as clear bullet lists (e.g. "- **w**: Weight (slope)", "- **b**: Bias (y-intercept)").
5. Keep paragraphs focused, spaced, and easy to read.

Deliver a comprehensive, highly pedagogical lesson following these exact phases:

## 1. Introduction and Intuition
- Start with a compelling real-world scenario or fundamental motivation.
- Explain why this topic is vital to master.

## 2. Simple Explanation (ELI5)
- Explain the concept in simple, intuitive terms using a clear analogy.
- Break down the core mechanism step-by-step without unnecessary jargon.

## 3. In-Depth Mechanics and Worked Example
- Provide a concrete, step-by-step worked demonstration or rule breakdown.
- Highlight clean formulas and explain the rationale behind each step.
- Include structured subheadings and variable breakdowns.

## 4. Key Takeaways and Common Mistakes
- Summarize 3 critical rules to remember.
- Call out 1-2 common traps to avoid on exams.

## 5. Lesson Wrap-Up
- Give an encouraging conclusion and let the student know they are prepared for the examination!"""

DOUBT_RESOLUTION_PROMPT = """You are a patient, articulate AI professor.
The student has a doubt about the topic "{topic_title}".

MATERIAL CONTEXT:
{context}

STUDENT DOUBT:
{question}

Provide a direct, accurate, and deeply grounded explanation addressing their exact confusion.
CRITICAL FORMATTING:
- Write in clean, conversational, natural academic English.
- Use readable unicode math (e.g. "ŷ = w·x + b", "σ(z) = 1 / (1 + e⁻ᶻ)").
- DO NOT use any emojis.
- Conclude with a brief follow-up question or check for understanding to keep the session interactive.
"""


class TeachingEngine:
    """
    Orchestrates Normal Mode (JSON progressive cards) and Teacher Mode (Streamed lecture).
    """

    async def get_core_idea(
        self,
        topic_title: str,
        topic_summary: str = "",
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Returns structured 4-phase JSON steps for Normal Mode.
        """
        prompt = NORMAL_CORE_IDEA_PROMPT.format(
            topic_title=topic_title,
            topic_summary=topic_summary,
            context=context or "Standard academic foundations and formulations.",
        )

        messages = [
            {"role": "system", "content": "You are a professional academic curriculum engine. Return ONLY valid JSON without emojis."},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = await ollama.chat(messages, temperature=0.2)
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned.rsplit("\n", 1)[0]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()

            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1:
                cleaned = cleaned[start_idx : end_idx + 1]

            data = json.loads(cleaned)
            if "steps" in data and isinstance(data["steps"], list):
                return data
        except Exception as e:
            print(f"[TeachingEngine] JSON parse fallback: {e}")

        # Fallback structured steps
        return {
            "steps": [
                {
                    "step_id": "big_picture",
                    "step_number": 1,
                    "tag": "THE BIG PICTURE",
                    "title": "The Big Picture",
                    "subtitle": "High-level intuition and fundamental purpose",
                    "content": f"**{topic_title}** provides fundamental computational and analytical models designed to extract patterns, minimize prediction errors, and optimize decision boundaries."
                },
                {
                    "step_id": "core_principle",
                    "step_number": 2,
                    "tag": "CORE PRINCIPLE",
                    "title": "Core Principle and Mechanics",
                    "subtitle": "The governing rules and algorithmic mechanics",
                    "content": topic_summary or f"The core formulation of {topic_title} relies on objective loss minimization and iterative parameter updating."
                },
                {
                    "step_id": "key_takeaways",
                    "step_number": 3,
                    "tag": "KEY TAKEAWAYS",
                    "title": "Key Takeaways and Core Insights",
                    "subtitle": "High-yield takeaways to remember",
                    "content": "- **Representation**: Define feature vectors and target objectives clearly.\n- **Optimization**: Calculate gradients or analytical solutions to minimize loss.\n- **Generalization**: Evaluate against independent test distributions to avoid overfitting."
                },
                {
                    "step_id": "common_pitfall",
                    "step_number": 4,
                    "tag": "COMMON PITFALL",
                    "title": "Common Pitfalls and Exam Traps",
                    "subtitle": "Frequent student misconceptions and mistakes",
                    "content": "A common mistake is failing to verify model assumptions (such as linearity or feature independence) prior to fitting parameters."
                }
            ]
        }

    async def teach_topic_stream(
        self,
        topic_title: str,
        context: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Streams full 4-phase pedagogical lesson in Teacher Mode.
        """
        prompt = TEACHER_MODE_PROMPT.format(
            topic_title=topic_title,
            context=context or "Standard academic curriculum and worked formulations.",
        )

        messages = [
            {"role": "system", "content": "You are a distinguished university professor. Output clean, deeply structured markdown without any emojis."},
            {"role": "user", "content": prompt},
        ]

        async for chunk in ollama.chat_stream(messages, temperature=0.3):
            # Clean any accidental emojis
            sanitized_chunk = re.sub(r'[\U00010000-\U0010ffff]', '', chunk)
            yield sanitized_chunk

    async def answer_doubt(
        self,
        topic_title: str,
        question: str,
        context: str = "",
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Answers a specific doubt grounded in material context.
        """
        prompt = DOUBT_RESOLUTION_PROMPT.format(
            topic_title=topic_title,
            question=question,
            context=context or "Standard reference materials.",
        )

        messages = [
            {"role": "system", "content": "You are an articulate, supportive academic mentor. Answer clearly and concisely with clean mathematics and zero emojis."},
        ]

        if history:
            for h in history[-4:]:
                messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})

        messages.append({"role": "user", "content": prompt})

        res = await ollama.chat(messages, temperature=0.2)
        return re.sub(r'[\U00010000-\U0010ffff]', '', res).strip()


# Singleton
teaching_engine = TeachingEngine()
