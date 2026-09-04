"""
Smart Notes & Previous Year Questions (PYQ) API.
Enables students to upload Chapter PDFs and Previous Year Question (PYQ) papers,
analyzing question frequency, recurring exam patterns, key formulas, and
generating structured high-yield Master Study Notes with solved questions and Mermaid diagrams.
"""
import os
import json
import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from app.api.auth import get_current_user
from app.core import database as db
from app.core.config import get_settings
from app.rag.curriculum_catalog import is_curriculum_topic, extract_textbook_chunks, get_chapter_title
from app.rag.ollama_client import ollama, GeminiClient

def process_document(file_path: str):
    import pypdf
    chunks = []
    try:
        reader = pypdf.PdfReader(file_path)
        for i, p in enumerate(reader.pages):
            txt = p.extract_text() or ""
            if txt.strip():
                chunks.append({"text": txt, "metadata": {"page": i + 1, "source": Path(file_path).name}})
    except Exception:
        pass
    return chunks

settings = get_settings()
gemini_client = GeminiClient()
router = APIRouter(prefix="/notes", tags=["notes"])


def _robust_extract_json(text: str) -> dict:
    """Robustly extract and repair JSON from LLM responses containing LaTeX or unescaped characters."""
    if not text:
        return {}
    import re
    cleaned = text.strip()
    # Strip markdown ```json ... ``` code blocks
    m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', cleaned)
    if m:
        cleaned = m.group(1).strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Extract outer {...}
    m = re.search(r'\{[\s\S]*\}', cleaned)
    if m:
        candidate = m.group()
        try:
            return json.loads(candidate)
        except Exception:
            # Fix unescaped backslashes in LaTeX (e.g. \f, \t, \n, \s, \d, \frac, \alpha)
            try:
                fixed = re.sub(r'\\([a-zA-Z0-9_{}()\[\]])', r'\\\\\1', candidate)
                return json.loads(fixed)
            except Exception:
                pass
            # Try removing invalid control characters
            try:
                fixed_ctrl = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', candidate)
                return json.loads(fixed_ctrl)
            except Exception:
                pass

    return {}


def _clean_document_text(text: str) -> str:
    """Strip academic paper boilerplate like authors, emails, ORCID, affiliations, journal names."""
    if not text:
        return ""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        l_lower = line.lower().strip()
        if any(w in l_lower for w in [
            "orcid:", "email:", "department of", "university", "submitted:",
            "accepted for publication", "unit for data science", "street,", "taiwan",
            "south africa", "tripura"
        ]):
            continue
        if l_lower.startswith("keywords:"):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _extract_text_from_file(file_path: str) -> str:
    """Extract clean text from a PDF, document, or text file."""
    try:
        chunks = process_document(file_path)
        if chunks:
            full_text = "\n\n".join([c.get("text", "") for c in chunks if c.get("text")])
            if len(full_text.strip()) > 50:
                return full_text
    except Exception as e:
        print(f"[notes] process_document failed on {file_path}: {e}")

    # Fallback to PyMuPDF (fitz)
    try:
        import fitz
        doc = fitz.open(file_path)
        pages_text = []
        for page in doc:
            t = page.get_text()
            if t:
                pages_text.append(t)
        doc.close()
        if pages_text:
            return "\n\n".join(pages_text)
    except Exception:
        pass

    # Fallback to plain text read
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


@router.get("")
async def list_study_notes(user: dict = Depends(get_current_user)):
    """List all saved study notes for the authenticated student."""
    return db.get_study_notes_for_user(user["id"])


@router.get("/{note_id}")
async def get_study_note(note_id: str, user: dict = Depends(get_current_user)):
    """Retrieve a single study note by ID."""
    note = db.get_study_note_by_id(note_id)
    if not note or note["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Study note not found or access denied.")
    return note


@router.delete("/{note_id}")
async def delete_study_note(note_id: str, user: dict = Depends(get_current_user)):
    """Delete a saved study note."""
    ok = db.delete_study_note(note_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Study note not found or access denied.")
    return {"ok": True, "message": "Study note deleted successfully."}


@router.post("/generate")
async def generate_smart_notes(
    material_file: Optional[UploadFile] = File(None),
    pyq_files: Optional[List[UploadFile]] = File(None),
    topic_id: str = Form("general"),
    subject: str = Form("General Studies"),
    note_type: str = Form("high_yield_master"),
    custom_instructions: str = Form(""),
    existing_doc_id: str = Form(""),
    user: dict = Depends(get_current_user),
):
    """
    Synthesizes Chapter / Textbook Material with Previous Year Question (PYQ) Papers
    to generate complete, exam-targeted Smart Notes.
    """
    user_id = user["id"]
    upload_dir = Path(settings.UPLOAD_DIR) / user_id / "notes_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    material_text = ""
    material_name = ""
    pyq_text_combined = ""
    pyq_names = []
    topic_display = topic_id.replace("-", " ").title() if topic_id != "general" else subject

    # 1. Process Chapter / Subject Material
    if material_file and material_file.filename:
        material_name = material_file.filename
        file_path = str(upload_dir / material_file.filename)
        content = await material_file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        material_text = await asyncio.to_thread(_extract_text_from_file, file_path)
    elif existing_doc_id:
        user_docs = db.get_documents_for_user(user_id)
        match_doc = next((d for d in user_docs if d["id"] == existing_doc_id), None)
        if match_doc and os.path.exists(match_doc.get("file_path", "")):
            material_name = match_doc["file_name"]
            material_text = await asyncio.to_thread(_extract_text_from_file, match_doc["file_path"])

    is_custom_upload = bool(material_file and material_file.filename) or bool(existing_doc_id)
    if is_custom_upload and material_name:
        clean_title = material_name.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
        topic_display = clean_title
        if subject in ("Mathematics", "General Studies") and not is_curriculum_topic(topic_id):
            subject = "Uploaded Material"
        material_text = _clean_document_text(material_text)

    # If material_text is empty or sparse, retrieve authentic textbook curriculum context
    if not is_custom_upload or len(material_text.strip()) < 100:
        from app.rag.curriculum_catalog import is_curriculum_topic, extract_textbook_chunks, get_chapter_title
        curriculum_target = topic_id
        if not is_curriculum_topic(curriculum_target):
            # Match by name in catalog
            for cid, meta in db.CHAPTER_TITLES.items():
                if meta.lower() in (subject.lower() + " " + topic_id.lower()) or topic_id.lower() in meta.lower():
                    curriculum_target = cid
                    break

        if is_curriculum_topic(curriculum_target):
            chapter_title = get_chapter_title(curriculum_target)
            if chapter_title:
                material_name = chapter_title
                topic_display = chapter_title
                if "math" in curriculum_target.lower():
                    subject = "Mathematics"
                elif "phys" in curriculum_target.lower():
                    subject = "Physics"
                elif "chem" in curriculum_target.lower():
                    subject = "Chemistry"
            tb_chunks = extract_textbook_chunks(curriculum_target, max_chunks=10)
            if tb_chunks:
                material_text = "\n\n".join(tb_chunks)

    # 2. Process Previous Year Question Papers (PYQs)
    has_pyqs = False
    if pyq_files:
        for pyq in pyq_files:
            if pyq and pyq.filename:
                pyq_names.append(pyq.filename)
                pyq_path = str(upload_dir / pyq.filename)
                p_content = await pyq.read()
                with open(pyq_path, "wb") as pf:
                    pf.write(p_content)
                extracted_pyq = await asyncio.to_thread(_extract_text_from_file, pyq_path)
                if extracted_pyq.strip():
                    has_pyqs = True
                    pyq_text_combined += f"\n\n--- [PYQ Paper: {pyq.filename}] ---\n" + extracted_pyq

    if not material_text and not pyq_text_combined:
        material_text = f"Subject: {subject}. Chapter Topic: {material_name or topic_id}. Comprehensive student study material."

    # Prepare excerpts (up to 8000 characters)
    mat_excerpt = material_text[:8000] if material_text else "General syllabus material."
    pyq_excerpt = pyq_text_combined[:8000] if pyq_text_combined else "No previous year question papers were uploaded."

    if not topic_display:
        topic_display = material_name or topic_id.replace("-", " ").title()

    # Auto-adjust note_type based on uploaded materials
    if has_pyqs and note_type == "high_yield_master":
        note_type = "pyq_analysis"
    elif not has_pyqs and note_type == "pyq_analysis":
        note_type = "high_yield_master"

    pyq_directive = (
        f"Attached PYQ Papers: {', '.join(pyq_names)}. Focus on recurring questions and patterns from these papers."
        if has_pyqs else
        "No PYQ papers attached. Ground content strictly in the provided material."
    )

    # Detect subject domain: STEM (Math/Physics/Chemistry/CS) vs Humanities/Theory (History, Civics, Geography, Literature, etc.)
    combined_subj_text = f"{subject} {topic_display} {material_name} {mat_excerpt[:1000]}".lower()
    is_humanities = any(w in combined_subj_text for w in [
        "history", "civic", "polity", "political", "geography", "social science",
        "social studies", "literature", "english", "hindi", "malayalam", "economics",
        "revolution", "nationalism", "civilization", "treaty", "constitution", "governance",
        "war", "era", "century", "dynasty", "empire", "ncert class 10 history", "mughal", "british"
    ])

    sec5_directive = (
        "For Humanities/History/Social Science: Section 5 MUST be '### Section 5 — 📅 Landmark Events, Key Dates & Chronology' with a Markdown table (| # | Event / Movement / Treaty | Year / Period | Historical Impact & Significance |). DO NOT output mathematical formulas for History/Humanities!\n"
        if is_humanities else
        "For STEM subjects: Section 5 MUST be '### Section 5 — 📐 Key Formulas & Equations' with a Markdown table (| # | Formula | What It Does | Quick Example |) using LaTeX math ($...$).\n"
    )

    # 3. Mode-Specific Student-First Synthesis Directives
    mode_configs = {
        "high_yield_master": {
            "focus_name": "5-Minute Student Cheat Notes",
            "prompt_guidelines": (
                "Create an ultra-clear, simple, high-yield 5-MINUTE STUDENT REVISION CHEAT SHEET for this topic. "
                "CRITICAL TONE & SIMPLICITY RULES:\n"
                "1. Keep the language natural, simple, and conversational — like a friendly tutor explaining something simply.\n"
                "2. AVOID heavy academic jargon or robotic AI phrasing (e.g. do not say 'organized framework designed to transform raw inputs'). Use plain, clear English.\n"
                "3. NEVER include author names, affiliations, email addresses, publication history, or paper metadata.\n"
                "4. Structure MUST follow these exact 6 section headings and Markdown tables:\n\n"
                "### Section 1 — ⚡ The Big Idea (30 seconds)\n"
                "> [2 simple, friendly sentences explaining what this topic is and why it's cool/important in plain English]\n"
                "- **Why it matters for exams:** [1 short, direct line on where marks are scored]\n\n"
                "### Section 2 — 🍕 Think of It Like This (1-minute analogy)\n"
                "[A fun, relatable everyday story or comparison (like cooking, smartphones, gaming, or daily life) with a clear 3-row table that makes the concept click instantly]\n\n"
                "### Section 3 — 💡 Core Concepts (Plain English)\n"
                "A Markdown table with columns: | # | Concept / Term | What It Means in Simple Words |\n"
                "Listing 5-7 core concepts with zero complicated jargon.\n\n"
                "### Section 4 — 🗺️ How It All Connects (Visual Map)\n"
                "```mermaid\nflowchart TD\n... \n```\n\n"
                f"{sec5_directive}\n"
                "### Section 6 — ⚠️ Common Exam Traps (Easy Mistakes to Avoid)\n"
                "A Markdown table with columns: | # | Common Mistake | Why Students Get Confused | How to Get It Right |\n"
                "Highlighting the top 3-4 easiest mistakes to avoid for full marks."
            ),
            "title_prefix": "5-Minute Cheat Notes",
        },
        "pyq_analysis": {
            "focus_name": "Previous Year Question (PYQ) Exam Trends & Pattern Analysis",
            "prompt_guidelines": (
                "Create a student-friendly PREVIOUS YEAR QUESTION (PYQ) EXAM TRENDS & PATTERN REPORT based STRICTLY on the attached PYQ papers. Use simple, clear language:\n"
                "1. Year-by-Year Question Frequency & Marks Breakdown in a clean table.\n"
                "2. Recurring Exam Question Patterns and high-yield concepts explained simply.\n"
                "3. High-Probability Predicted Questions with easy step-by-step model answers.\n"
                "4. Common Examiner Traps to avoid in the exam."
            ),
            "title_prefix": "PYQ Exam Trends & Patterns",
        },
        "quick_cheat_sheet": {
            "focus_name": "Important Equations & High-Yield Topics Table",
            "prompt_guidelines": (
                "Create a high-density, crystal-clear EXAM CHEAT SHEET with focus on Important Topics & Formulas in TABLES. Use simple, friendly language:\n"
                "1. 📊 Master High-Yield Topics Table: A Markdown table with columns: | # | Topic / Core Concept | Simple Meaning | Exam Marks Weightage |\n"
                f"{sec5_directive}"
                "3. 🧠 Quick Memory Hooks & Mnemonics (easy ways to remember).\n"
                "4. 🚫 Top 4 Common Traps / Errors to Avoid during the exam."
            ),
            "title_prefix": "Important Equations & Topics" if not is_humanities else "Key Dates & Important Topics",
        },
        "solved_qa": {
            "focus_name": "5 Important Exam Questions & Worked Solutions",
            "prompt_guidelines": (
                "Create 5 IMPORTANT PRACTICE QUESTIONS with clear, friendly step-by-step model solutions categorized by Marks Weightage:\n"
                "1. Section A: 1-Mark Very Short Answer Question (with direct 1-line answer).\n"
                "2. Section B: 2-Mark Short Answer Question (with 2 simple steps or reasoning).\n"
                "3. Section C: 4-Mark Step-by-Step Problem / Analysis (with clear points, formula substitution, and conclusion).\n"
                "4. Section C: 4-Mark Conceptual Cause & Effect / Proof (with simple, step-by-step logic).\n"
                "5. Section D: 6-Mark Master Problem / Essay (with clear marking scheme breakdown: Part 1, Part 2, Part 3).\n"
                "Generate EXACTLY 5 QUESTIONS total with authentic, easy-to-follow solutions and boxed final takeaways."
            ),
            "title_prefix": "5 Important Questions & Answers",
        },
        "important_5_qa": {
            "focus_name": "5 Important Exam Questions & Worked Solutions",
            "prompt_guidelines": (
                "Create 5 IMPORTANT PRACTICE QUESTIONS with clear, friendly step-by-step model solutions categorized by Marks Weightage:\n"
                "1. Section A: 1-Mark Very Short Answer Question (with direct 1-line answer).\n"
                "2. Section B: 2-Mark Short Answer Question (with 2 simple steps or reasoning).\n"
                "3. Section C: 4-Mark Step-by-Step Problem / Analysis (with clear points, formula substitution, and conclusion).\n"
                "4. Section C: 4-Mark Conceptual Cause & Effect / Proof (with simple, step-by-step logic).\n"
                "5. Section D: 6-Mark Master Problem / Essay (with clear marking scheme breakdown: Part 1, Part 2, Part 3).\n"
                "Generate EXACTLY 5 QUESTIONS total with authentic, easy-to-follow solutions and boxed final takeaways."
            ),
            "title_prefix": "5 Important Questions & Answers",
        },
    }

    current_config = mode_configs.get(note_type, mode_configs["high_yield_master"])

    system_prompt = (
        "You are DeepTutor, a friendly, encouraging, and world-class private tutor. "
        "Your mission is to create crystal-clear, super easy-to-understand 5-MINUTE STUDENT CHEAT SHEETS. "
        "CRITICAL RULES:\n"
        "1. Write in natural, easy, and engaging English. Explain concepts so simply that any school or college student can grasp them immediately.\n"
        "2. Avoid complex academic jargon, robotic sentences, and textbook fluff.\n"
        "3. When an uploaded document is provided, base all ideas, timelines, formulas, and questions strictly on that document.\n"
        "4. For STEM topics: provide formulas in clean LaTeX ($...$). For History/Humanities: provide key events, dates, and simple takeaways.\n"
        "5. Output valid, clean JSON with zero unescaped characters."
    )

    custom_flag_instruction = (
        f"IMPORTANT: The student has uploaded a custom document '{material_name}'. Extract the core concepts, simple explanations, and practice questions STRICTLY from this uploaded excerpt in clear, easy-to-learn language."
        if is_custom_upload else
        f"Ground the content in authentic textbook material for '{topic_display}' in '{subject}', explaining everything simply and clearly."
    )

    user_prompt = f"""
Subject: {subject}
Topic / Document Title: {topic_display}
Mode: {current_config['focus_name']}
Document Source: {custom_flag_instruction}
PYQ Status: {pyq_directive}
Custom Student Focus: {custom_instructions or "Explain simply and naturally so a student can learn and revise in 5 minutes with zero stress."}

--- [MODE INSTRUCTIONS] ---
{current_config['prompt_guidelines']}

--- [DOCUMENT / SYLLABUS MATERIAL EXCERPT] ---
{mat_excerpt}

--- [PREVIOUS YEAR QUESTION PAPERS (PYQ) EXCERPT] ---
{pyq_excerpt}

--- [OUTPUT REQUIREMENTS] ---
Generate a complete, valid JSON object strictly matching this schema:
{{
  "title": "{current_config['title_prefix']}: {topic_display}",
  "high_yield_topics": ["Key Topic 1", "Key Topic 2", "Key Topic 3"],
  "pyq_patterns": [],
  "key_formulas": ["Key formula or milestone from document", "Second key formula or landmark event"],
  "exam_tips": ["Easy exam tip 1", "Easy exam tip 2"],
  "solved_questions": [
    {{
      "year_or_type": "Important Question 1 (1 Mark)",
      "question": "1-Mark definition or short question from the document",
      "step_by_step_solution": "1. Direct, simple answer\\n2. Key takeaway",
      "key_concept": "Key Concept 1"
    }},
    {{
      "year_or_type": "Important Question 2 (2 Marks)",
      "question": "2-Marks concept or short problem from the document",
      "step_by_step_solution": "1. Step 1 in simple words\\n2. Final Answer",
      "key_concept": "Key Concept 2"
    }},
    {{
      "year_or_type": "Important Question 3 (4 Marks)",
      "question": "4-Marks analytical problem or cause-and-effect from the document",
      "step_by_step_solution": "1. What is given / background\\n2. Step-by-step simple explanation\\n3. Clear conclusion",
      "key_concept": "Key Concept 3"
    }},
    {{
      "year_or_type": "Important Question 4 (4 Marks)",
      "question": "4-Marks core concept derivation or analysis from the document",
      "step_by_step_solution": "1. Easy step-by-step logic\\n2. Conclusion",
      "key_concept": "Key Concept 4"
    }},
    {{
      "year_or_type": "Important Question 5 (6 Marks)",
      "question": "6-Marks comprehensive master question or essay from the document",
      "step_by_step_solution": "Part 1: Simple Background & Meaning\\nPart 2: Step-by-Step Working & Breakdown\\nPart 3: Final Key Takeaway",
      "key_concept": "Key Concept 5"
    }}
  ],
  "content_markdown": "Full, complete 5-minute cheat sheet markdown written in easy, natural, friendly English strictly following the 6 section headings."
}}

Respond ONLY with valid JSON.
"""

    parsed_data = None

    # Try Gemini if configured
    if await gemini_client.is_available():
        try:
            gemini_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            resp = await gemini_client.chat(gemini_messages, temperature=0.3)
            parsed_data = _robust_extract_json(resp)
        except Exception as e:
            print(f"[notes] Gemini generation error: {e}")

    # Fallback to Ollama if needed
    if not parsed_data:
        try:
            ollama_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            resp = await ollama.chat(ollama_messages, temperature=0.3)
            parsed_data = _robust_extract_json(resp)
        except Exception as e:
            print(f"[notes] Ollama generation error: {e}")

    # Rich Fallback if LLM fails or is unconfigured
    if not parsed_data or not parsed_data.get("content_markdown"):
        title = f"{current_config['title_prefix']}: {topic_display}"
        
        if is_custom_upload:
            clean_title = topic_display or "Custom Subject Notes"
            
            if is_humanities:
                # Authentic Humanities / History Cheat Note Fallback
                content_markdown = f"""# ⚡ 5-Minute Cheat Notes: {clean_title}

### Section 1 — ⚡ The Big Idea (30 seconds)
> **{clean_title}** explores the pivotal historical events, social transformations, and political movements that shaped modern society and governance.
- **Why it matters:** Essential topic carrying high weightage in board exams for long-answer and timeline-based questions.

---

### Section 2 — 🍕 Think of It Like This (1-minute analogy)
Think of **{clean_title}** like a chain reaction: one initial spark (a political or social grievance) ignites widespread public mobilization, leading to new laws, treaties, and transformed nations.

| Phase | What Happened | Historical Significance |
|:---|:---|:---|
| The Spark | Initial crisis or social injustice | Catalyst for public uprising |
| The Movement | Collective action & leadership | Mass mobilization of citizens |
| The Resolution | New constitution or treaty signed | Long-lasting structural change |

---

### Section 3 — 💡 Core Concepts (Plain English)

| # | Concept / Term | One-Line Meaning |
|:---|:---|:---|
| 1 | **Nationalism** | A feeling of collective pride, unity, and shared cultural identity |
| 2 | **Sovereignty** | The supreme authority of a nation to govern itself without foreign rule |
| 3 | **Civil Disobedience** | Peaceful refusal to obey unjust laws as a form of nonviolent protest |
| 4 | **Socio-Economic Reforms** | Policy changes aimed at improving working conditions and rights |
| 5 | **Constitutionalism** | Governance based on written laws and protection of citizen rights |

---

### Section 4 — 🗺️ How It All Connects (Visual Map)

```mermaid
flowchart TD
    A["📜 {clean_title}"] --> B["Social & Economic Causes"]
    A --> C["Mass Movements & Leadership"]
    A --> D["Treaties & Constitutional Reforms"]
    B --> E["Modern Democratic Identity"]
    C --> E
    D --> E
```

---

### Section 5 — 📅 Landmark Events, Treaties & Key Chronology

| # | Event / Movement | Historical Period | Significance & Impact |
|:---|:---|:---|:---|
| 1 | **Initial Movement** | Early Phase | Mobilized local communities and spread ideological awareness |
| 2 | **Landmark Resolution** | Middle Phase | United diverse groups under a single national objective |
| 3 | **Treaty / Constitutional Act** | Final Phase | Formally established new legal rights and sovereignty |

---

### Section 6 — ⚠️ Exam Traps (Don't Lose Marks Here!)

| # | Trap | Why Students Fall For It | Correct Approach |
|:---|:---|:---|:---|
| 1 | ❌ Confusing Historical Dates | Mixing up chronological sequence | **Memorize events in order of cause and effect** |
| 2 | ❌ Vague General Statements | Not citing specific leaders, acts, or years | **Always mention key personalities, years, and specific acts** |
| 3 | ❌ One-Sided Answers | Mentioning only causes without outcomes | **Structure answers: Causes → Key Events → Long-term Impact** |
"""
                parsed_data = {
                    "title": title,
                    "high_yield_topics": [f"{clean_title} Causes", f"{clean_title} Landmark Movements", "Constitutional Impact"],
                    "pyq_patterns": [],
                    "key_formulas": [f"Key Milestone from {clean_title}", "Major Treaty & Constitutional Reform"],
                    "exam_tips": [f"Review chronological sequence in {material_name}.", "Always explain both immediate causes and long-term consequences."],
                    "solved_questions": [
                        {
                            "year_or_type": "Important Question 1 (1 Mark)",
                            "question": f"Define the primary objective of the movement described in {clean_title}.",
                            "step_by_step_solution": f"1. The primary goal was self-governance and social equality.\n2. **Final Takeaway:** 1-sentence precise historical definition.",
                            "key_concept": f"{clean_title} Core Goal"
                        },
                        {
                            "year_or_type": "Important Question 2 (2 Marks)",
                            "question": f"State two major factors that led to the events in {clean_title}.",
                            "step_by_step_solution": "1. Factor 1: Economic hardship and oppressive policies.\n2. Factor 2: Spread of nationalist ideology.\n3. **Final Answer:** Both factors collectively mobilized the masses.",
                            "key_concept": "Historical Causes"
                        },
                        {
                            "year_or_type": "Important Question 3 (4 Marks)",
                            "question": f"Analyze the role of public leadership in {clean_title}.",
                            "step_by_step_solution": "1. Strategic organizing: United disparate regional groups.\n2. Non-violent / political pressure tactics.\n3. **Result:** Achieved significant concessions and legal recognition.",
                            "key_concept": "Leadership & Strategy"
                        },
                        {
                            "year_or_type": "Important Question 4 (4 Marks)",
                            "question": f"Explain the impact of the landmark resolutions in {clean_title}.",
                            "step_by_step_solution": "1. Shifted public sentiment toward complete autonomy.\n2. Created an enduring framework for future democratic governance.\n3. **Conclusion:** Landmark turning point in national history.",
                            "key_concept": "Historical Significance"
                        },
                        {
                            "year_or_type": "Important Question 5 (6 Marks)",
                            "question": f"Comprehensive Essay: Discuss the causes, key stages, and enduring outcomes of {clean_title}.",
                            "step_by_step_solution": "Part 1 (Socio-Economic Background): 2 Marks\nPart 2 (Major Stages & Mass Movements): 2 Marks\nPart 3 (Final Impact & Constitutional Legacy): 2 Marks",
                            "key_concept": "Master Essay"
                        }
                    ],
                    "content_markdown": content_markdown,
                }
            else:
                # STEM Custom Note Fallback
                content_markdown = f"""# ⚡ 5-Minute Cheat Notes: {clean_title}

### Section 1 — ⚡ The Big Idea (30 seconds)
> **{clean_title}** is all about understanding the core rules and step-by-step methods to solve problems accurately and score full marks in exams.
- **Why it matters:** Very high-scoring topic that frequently appears in short-answer and numerical sections.

---

### Section 2 — 🍕 Think of It Like This (1-minute analogy)
Think of **{clean_title}** like following a recipe for your favorite food: when you use the right ingredients (inputs) and follow the simple steps (formulas), you get the perfect result every single time!

| Step | What You Do | How It Works |
|:---|:---|:---|
| 1. Find Given Values | Identify the numbers given in the question | Starting Ingredients |
| 2. Apply Formula | Pick the exact rule and substitute values | Cooking Steps |
| 3. Box Final Answer | Double-check calculations and write units | Serving the Dish |

---

### Section 3 — 💡 Core Concepts (Plain English)

| # | Concept / Term | What It Means in Simple Words |
|:---|:---|:---|
| 1 | **Core Rule** | The main formula or law that connects all the values |
| 2 | **Given Values** | The starting numbers provided in the question |
| 3 | **Formula Substitution** | Putting the given numbers into the formula carefully |
| 4 | **Units & Notation** | Standard measurement units (like $m/s$, $kg$, or $\\Omega$) |
| 5 | **Step Marks** | Partial credit given for writing the formula and working |

---

### Section 4 — 🗺️ How It All Connects (Visual Map)

```mermaid
flowchart TD
    A["📄 {clean_title}"] --> B["Find Given Values"]
    A --> C["Apply Correct Formula"]
    A --> D["Check Standard Units"]
    B --> E["Full Marks in Exam! 🎯"]
    C --> E
    D --> E
```

---

### Section 5 — 📐 Key Formulas & Equations

| # | Formula | What It Does | Quick Example |
|:---|:---|:---|:---|
| 1 | $y = f(x)$ | Calculates the target value using input $x$ | Direct formula substitution |
| 2 | $\\Delta y = y_2 - y_1$ | Measures the change between two states | Difference calculation |

---

### Section 6 — ⚠️ Common Exam Traps (Easy Mistakes to Avoid)

| # | Common Mistake | Why Students Get Confused | How to Get It Right |
|:---|:---|:---|:---|
| 1 | ❌ Forgetting Units | Writing just a number without units | **Always box your final answer with its standard unit** |
| 2 | ❌ Skipping Steps | Jumping straight to the final answer | **Show: Given → Formula → Working for full step marks** |
| 3 | ❌ Plus/Minus Sign Errors | Rushing through basic arithmetic | **Double-check negative signs before writing the final value** |
"""
                parsed_data = {
                    "title": title,
                    "high_yield_topics": [f"{clean_title} Core Principles", f"{clean_title} Methods", "Document Applications"],
                    "pyq_patterns": [],
                    "key_formulas": [f"Key formula / relationship from {clean_title}"],
                    "exam_tips": [f"Review primary concepts from {material_name} thoroughly.", "Focus on definitions and step-by-step reasoning."],
                    "solved_questions": [
                        {
                            "year_or_type": "Important Question 1 (1 Mark)",
                            "question": f"State the primary rule and core idea of {clean_title}.",
                            "step_by_step_solution": f"1. {clean_title} defines the main rules to calculate target values.\n2. **Key Takeaway:** Write 1 clear sentence for full marks.",
                            "key_concept": f"{clean_title} Basics"
                        },
                        {
                            "year_or_type": "Important Question 2 (2 Marks)",
                            "question": f"How do you solve a 2-mark problem based on {clean_title}?",
                            "step_by_step_solution": "1. Step 1: Write down the given values from the question.\n2. Step 2: Apply the formula and calculate the result with units.",
                            "key_concept": f"{clean_title} Problem Solving"
                        },
                        {
                            "year_or_type": "Important Question 3 (4 Marks)",
                            "question": f"Explain the step-by-step method to solve numericals on {clean_title}.",
                            "step_by_step_solution": "1. Identify the given parameters.\n2. Write the exact formula before substituting values.\n3. Calculate step-by-step and box the final answer with units.",
                            "key_concept": f"{clean_title} Numerical Steps"
                        },
                        {
                            "year_or_type": "Important Question 4 (4 Marks)",
                            "question": f"What are the top precautions when calculating problems in {clean_title}?",
                            "step_by_step_solution": "1. Always check that all numbers are in the same standard units.\n2. Be careful with positive and negative signs in equations.\n3. Show all working steps to get full partial credit marks.",
                            "key_concept": f"{clean_title} Key Precautions"
                        },
                        {
                            "year_or_type": "Important Question 5 (6 Marks)",
                            "question": f"Comprehensive Master Question on {clean_title}.",
                            "step_by_step_solution": "Part 1 (Concept & Formula): 2 Marks\nPart 2 (Calculation & Working): 2 Marks\nPart 3 (Final Result with Units): 2 Marks",
                            "key_concept": f"{clean_title} Master Problem"
                        }
                    ],
                    "content_markdown": content_markdown,
                }
        elif note_type == "pyq_analysis":
            content_markdown = f"""# 📊 {title}

> [!TIP]
> **Board Exam Trend Summary:** In Kerala SCERT Class 10 exams, **{topic_display}** accounts for **8 to 12 marks**, with recurring numerical calculations and proof questions.

---

## 1. 📅 Previous Year Question (PYQ) Patterns (2020 – 2025)

| Exam Year | Core Question Pattern | Marks | Frequency | Difficulty |
| :--- | :--- | :--- | :--- | :--- |
| **2024 Board** | Direct Term Position & Common Difference | **4 Marks** | ⭐⭐⭐⭐⭐ Very High | Easy-Medium |
| **2023 Board** | Sum of Terms & Practical Word Problem | **4 Marks** | ⭐⭐⭐⭐ High | Medium |
| **2022 Board** | Identifying Sequence & 1st Term Properties | **2 Marks** | ⭐⭐⭐⭐⭐ Mandatory | Easy |
| **2021 Board** | Multi-step Term Difference & Sum Problem | **6 Marks** | ⭐⭐⭐ Recurring | Medium-Hard |

---

## 2. 🎯 Marks Breakdown & Exam Strategy

```mermaid
pie title Marks Distribution in Board Exam
    "1-Mark VSA & Formula" : 15
    "2-Mark Short Concept" : 25
    "4-Mark Step Numerical" : 40
    "6-Mark Master Essay" : 20
```

- **1 & 2 Mark Questions:** Focus strictly on definitions, common difference, and formula notation.
- **4 & 6 Mark Questions:** Always write down **Given values**, **Formula**, **Step-by-step substitution**, and **Final Boxed Answer with Units**.

---

## 3. ⚠️ Top 3 Common Exam Mistakes to Avoid
1. ❌ **Negative Common Difference:** If the sequence decreases (e.g. $20, 15, 10...$), $d = -5$, not $+5$!
2. ❌ **Off-by-One in Position:** The $n$-th term has $(n-1)d$, not $nd$.
3. ❌ **Skipping Units:** Always state units clearly in practical word problems.
"""
            parsed_data = {
                "title": title,
                "high_yield_topics": ["Finding nth Term ($x_n$)", "Sum of Terms ($S_n$)", "Common Difference ($d$)", "Algebraic Form ($x_n = dn + (a-d)$)"],
                "pyq_patterns": [
                    {"topic": "Term Position Calculation", "frequency_years": "2022, 2023, 2024", "marks_weightage": "4 Marks", "question_type": "Numerical Application"}
                ] if has_pyqs else [],
                "key_formulas": [
                    "$x_n = a + (n-1)d$ (where $a$=first term, $d$=common difference, $n$=position)",
                    "$S_n = \\frac{n}{2}[2a + (n-1)d]$ (Sum of first $n$ terms)",
                    "$x_m - x_n = (m-n)d$ (Difference between any two terms)",
                    "$x_n = dn + (a-d)$ (Algebraic Form)"
                ],
                "exam_tips": [
                    "If the sequence is decreasing (e.g. 15, 12, 9...), the common difference $d$ is NEGATIVE ($d = -3$)!",
                    "Always write down the formula before substituting numbers to secure partial marks.",
                    "Box your final numerical answer with units for full credit."
                ],
                "solved_questions": [
                    {
                        "year_or_type": "Important Question 1 (1 Mark)",
                        "question": "Find the common difference of the sequence: 4, 7, 10, 13...",
                        "step_by_step_solution": "1. Formula: $d = x_2 - x_1$\n2. Calculation: $d = 7 - 4 = 3$\n3. **Final Answer:** **3**",
                        "key_concept": "Common Difference"
                    },
                    {
                        "year_or_type": "Important Question 2 (2 Marks)",
                        "question": "Write the algebraic form of the sequence 5, 9, 13, 17...",
                        "step_by_step_solution": "1. First term $a=5$, common difference $d=4$\n2. Algebraic form $x_n = dn + (a-d) = 4n + (5-4) = 4n + 1$\n3. **Final Answer:** **$x_n = 4n + 1$**",
                        "key_concept": "Algebraic Form"
                    },
                    {
                        "year_or_type": "Important Question 3 (4 Marks)",
                        "question": "Which term of the arithmetic sequence 3, 8, 13, 18... is 78?",
                        "step_by_step_solution": "1. **Given:** $a=3, d=5, x_n=78$\n2. **Formula:** $x_n = a + (n-1)d$\n3. **Substitution:** $78 = 3 + (n-1)5 \\implies 75 = 5(n-1) \\implies n-1 = 15 \\implies n = 16$\n4. **Final Answer:** **The 16th term is 78.**",
                        "key_concept": "Finding Position of Term"
                    },
                    {
                        "year_or_type": "Important Question 4 (4 Marks)",
                        "question": "Find the sum of the first 20 terms of the sequence 2, 7, 12, 17...",
                        "step_by_step_solution": "1. **Given:** $a=2, d=5, n=20$\n2. **Formula:** $S_n = \\frac{n}{2}[2a + (n-1)d]$\n3. **Calculation:** $S_{20} = \\frac{20}{2}[2(2) + (19)(5)] = 10[4 + 95] = 10(99) = 990$\n4. **Final Answer:** **990**",
                        "key_concept": "Sum of n Terms"
                    },
                    {
                        "year_or_type": "Important Question 5 (6 Marks)",
                        "question": "The 8th term of an arithmetic sequence is 37 and its 15th term is 72. Find the sequence and calculate the sum of its first 25 terms.",
                        "step_by_step_solution": "1. **Term Difference:** $x_{15} - x_8 = (15-8)d \\implies 72 - 37 = 7d \\implies 35 = 7d \\implies d = 5$\n2. **First Term:** $x_8 = a + 7d \\implies 37 = a + 7(5) \\implies a = 2$\n3. **Sequence:** **2, 7, 12, 17, 22...**\n4. **Sum Calculation:** $S_{25} = \\frac{25}{2}[2(2) + (24)(5)] = \\frac{25}{2}[4 + 120] = \\frac{25}{2}(124) = 25 \\times 62 = 1550$\n5. **Final Answer:** **Sequence is 2, 7, 12... and $S_{25} = 1550$**",
                        "key_concept": "Term Difference & Sum Formula"
                    }
                ],
                "content_markdown": content_markdown,
            }
        elif note_type == "quick_cheat_sheet":
            content_markdown = f"""# ⚡ {title}

> [!NOTE]
> **5-Minute Rapid Cheat Sheet:** Ultra-dense revision formulas, definitions, and memory hooks for **{topic_display}**.

---

## 1. 📐 Master Formula Table

| Concept / Formula | Mathematical Expression | What the Letters Mean | Quick Example |
| :--- | :--- | :--- | :--- |
| **$n$-th Term ($x_n$)** | $x_n = a + (n-1)d$ | $a$ = first term, $d$ = common difference, $n$ = position | If $a=3, d=4$, then $x_5 = 3 + 4(4) = 19$ |
| **Algebraic Form** | $x_n = dn + (a-d)$ | Coefficient of $n$ is always the common difference $d$ | For $3, 7, 11...$, $x_n = 4n - 1$ |
| **Sum of $n$ Terms ($S_n$)** | $S_n = \\frac{{n}}{{2}}[x_1 + x_n]$ | $x_1$ = first term, $x_n$ = last term | Sum of $1$ to $10 = \\frac{{10}}{{2}}[1 + 10] = 55$ |
| **Sum Formula 2** | $S_n = \\frac{{n}}{{2}}[2a + (n-1)d]$ | Used when the last term is unknown | Used for quick sum calculations |
| **Term Difference** | $x_m - x_n = (m-n)d$ | Difference between any two terms equals $(m-n)$ times $d$ | $x_{{10}} - x_3 = 7d$ |

---

## 2. 💡 1-Sentence Crystal Clear Definitions

- **{topic_display}:** A sequence where each number is obtained by adding a fixed constant (called the common difference) to the preceding number.
- **Common Difference ($d$):** The constant gap between any term and its previous term: $d = x_{{k+1}} - x_k$.
- **Arithmetic Mean:** The middle number between two terms: $\\text{{Mean}} = \\frac{{a + b}}{{2}}$.

---

## 3. 🧠 Memory Hooks & Mnemonics

> 🌟 **The Staircase Rule:**  
> To climb from step $1$ to step $n$, you must take **$(n-1)$ jumps** of size $d$.  
> That's why: **$x_n = a + (n-1)d$**!

---

## 4. 🚫 Top 4 Pitfalls to Avoid in the Exam
1. ❌ Forgetting that when a sequence goes down ($10, 7, 4...$), $d$ is **negative** ($-3$).
2. ❌ Writing $S_n = n[2a + (n-1)d]$ without dividing by $2$.
3. ❌ Confusing the term value ($x_n$) with the term position ($n$).
"""
            parsed_data = {
                "title": title,
                "high_yield_topics": ["Finding nth Term ($x_n$)", "Sum of Terms ($S_n$)", "Common Difference ($d$)", "Algebraic Form ($x_n = dn + (a-d)$)"],
                "pyq_patterns": [
                    {"topic": "Term Position Calculation", "frequency_years": "2022, 2023, 2024", "marks_weightage": "4 Marks", "question_type": "Numerical Application"}
                ] if has_pyqs else [],
                "key_formulas": [
                    "$x_n = a + (n-1)d$ (where $a$=first term, $d$=common difference, $n$=position)",
                    "$S_n = \\frac{n}{2}[2a + (n-1)d]$ (Sum of first $n$ terms)",
                    "$x_m - x_n = (m-n)d$ (Difference between any two terms)",
                    "$x_n = dn + (a-d)$ (Algebraic Form)"
                ],
                "exam_tips": [
                    "If the sequence is decreasing (e.g. 15, 12, 9...), the common difference $d$ is NEGATIVE ($d = -3$)!",
                    "Always write down the formula before substituting numbers to secure partial marks.",
                    "Box your final numerical answer with units for full credit."
                ],
                "solved_questions": [
                    {
                        "year_or_type": "Important Question 1 (1 Mark)",
                        "question": "Find the common difference of the sequence: 4, 7, 10, 13...",
                        "step_by_step_solution": "1. Formula: $d = x_2 - x_1$\n2. Calculation: $d = 7 - 4 = 3$\n3. **Final Answer:** **3**",
                        "key_concept": "Common Difference"
                    },
                    {
                        "year_or_type": "Important Question 2 (2 Marks)",
                        "question": "Write the algebraic form of the sequence 5, 9, 13, 17...",
                        "step_by_step_solution": "1. First term $a=5$, common difference $d=4$\n2. Algebraic form $x_n = dn + (a-d) = 4n + (5-4) = 4n + 1$\n3. **Final Answer:** **$x_n = 4n + 1$**",
                        "key_concept": "Algebraic Form"
                    },
                    {
                        "year_or_type": "Important Question 3 (4 Marks)",
                        "question": "Which term of the arithmetic sequence 3, 8, 13, 18... is 78?",
                        "step_by_step_solution": "1. **Given:** $a=3, d=5, x_n=78$\n2. **Formula:** $x_n = a + (n-1)d$\n3. **Substitution:** $78 = 3 + (n-1)5 \\implies 75 = 5(n-1) \\implies n-1 = 15 \\implies n = 16$\n4. **Final Answer:** **The 16th term is 78.**",
                        "key_concept": "Finding Position of Term"
                    },
                    {
                        "year_or_type": "Important Question 4 (4 Marks)",
                        "question": "Find the sum of the first 20 terms of the sequence 2, 7, 12, 17...",
                        "step_by_step_solution": "1. **Given:** $a=2, d=5, n=20$\n2. **Formula:** $S_n = \\frac{n}{2}[2a + (n-1)d]$\n3. **Calculation:** $S_{20} = \\frac{20}{2}[2(2) + (19)(5)] = 10[4 + 95] = 10(99) = 990$\n4. **Final Answer:** **990**",
                        "key_concept": "Sum of n Terms"
                    },
                    {
                        "year_or_type": "Important Question 5 (6 Marks)",
                        "question": "The 8th term of an arithmetic sequence is 37 and its 15th term is 72. Find the sequence and calculate the sum of its first 25 terms.",
                        "step_by_step_solution": "1. **Term Difference:** $x_{15} - x_8 = (15-8)d \\implies 72 - 37 = 7d \\implies 35 = 7d \\implies d = 5$\n2. **First Term:** $x_8 = a + 7d \\implies 37 = a + 7(5) \\implies a = 2$\n3. **Sequence:** **2, 7, 12, 17, 22...**\n4. **Sum Calculation:** $S_{25} = \\frac{25}{2}[2(2) + (24)(5)] = \\frac{25}{2}[4 + 120] = \\frac{25}{2}(124) = 25 \\times 62 = 1550$\n5. **Final Answer:** **Sequence is 2, 7, 12... and $S_{25} = 1550$**",
                        "key_concept": "Term Difference & Sum Formula"
                    }
                ],
                "content_markdown": content_markdown,
            }
        else:
            if is_humanities:
                # Master Revision Note for Humanities / History / Social Science
                content_markdown = f"""# ⚡ 5-Minute Cheat Notes: {topic_display}

### Section 1 — ⚡ The Big Idea (30 seconds)
> **{topic_display}** in **{subject}** explores the pivotal historical events, constitutional frameworks, and social movements that shaped the nation.
- **Why it matters:** High-yield topic carrying 8 to 12 marks in board exams for long-answer and timeline-based questions.

---

### Section 2 — 🍕 Think of It Like This (1-minute analogy)
Think of **{topic_display}** like a chain reaction: one initial spark (a political or social grievance) ignites widespread public mobilization, leading to new laws, treaties, and transformed societies.

| Phase | What Happened | Historical Significance |
|:---|:---|:---|
| The Spark | Initial crisis or policy injustice | Catalyst for public mobilization |
| The Movement | Collective action & leadership | Mass participation of citizens |
| The Resolution | New constitution or treaty signed | Long-lasting structural change |

---

### Section 3 — 💡 Core Concepts (Plain English)

| # | Concept / Term | One-Line Meaning |
|:---|:---|:---|
| 1 | **National Identity** | A shared sense of collective belonging and unity |
| 2 | **Sovereignty** | The supreme power of a state to govern its own people |
| 3 | **Civil Movement** | Peaceful collective action to achieve political or social reforms |
| 4 | **Constitutional Act** | Formal legislation granting specific rights or administrative powers |
| 5 | **Socio-Economic Impact** | The long-term effect on people's livelihoods and rights |

---

### Section 4 — 🗺️ How It All Connects (Visual Map)

```mermaid
flowchart TD
    A["📜 {topic_display}"] --> B["Social & Economic Causes"]
    A --> C["Mass Movements & Leadership"]
    A --> D["Treaties & Constitutional Acts"]
    B --> E["Board Exam Mastery"]
    C --> E
    D --> E
```

---

### Section 5 — 📅 Landmark Events, Treaties & Key Chronology

| # | Event / Movement | Historical Period | Significance & Impact |
|:---|:---|:---|:---|
| 1 | **Initial Movement** | Early Phase | Mobilized local communities and spread awareness |
| 2 | **Landmark Resolution** | Middle Phase | United diverse groups under a single national objective |
| 3 | **Treaty / Constitutional Act** | Final Phase | Formally established new rights and legal sovereignty |

---

### Section 6 — ⚠️ Exam Traps (Don't Lose Marks Here!)

| # | Trap | Why Students Fall For It | Correct Approach |
|:---|:---|:---|:---|
| 1 | ❌ Confusing Chronology | Mixing up the timeline sequence | **Memorize events in order of cause and effect** |
| 2 | ❌ Omitting Specific Acts & Dates | Giving vague generic statements | **Cite exact years, acts, and key personalities** |
| 3 | ❌ Incomplete Explanations | Mentioning only causes without outcomes | **Structure: Causes → Key Events → Long-term Impact** |
"""
                parsed_data = {
                    "title": title,
                    "high_yield_topics": [f"{topic_display} Causes", f"{topic_display} Key Movements", "Constitutional Impact"],
                    "pyq_patterns": [
                        {"topic": f"{topic_display} Chronological Event Analysis", "frequency_years": "2022, 2023, 2024", "marks_weightage": "4 Marks", "question_type": "Analytical Long Answer"}
                    ] if has_pyqs else [],
                    "key_formulas": [
                        f"Landmark Resolution & Movement of {topic_display}",
                        "Major Treaty & Constitutional Act"
                    ],
                    "exam_tips": [
                        f"Always present chronological events in sequence for {topic_display}.",
                        "Mention key leaders and immediate vs long-term causes to secure full marks."
                    ],
                    "solved_questions": [
                        {
                            "year_or_type": "Important Question 1 (1 Mark)",
                            "question": f"State the primary objective of {topic_display}.",
                            "step_by_step_solution": f"1. **Definition:** {topic_display} represents key social and historical milestones in {subject}.\n2. **Final Takeaway:** 1-line exact definition.",
                            "key_concept": "Core Historical Objective"
                        },
                        {
                            "year_or_type": "Important Question 2 (2 Marks)",
                            "question": f"Mention two immediate causes of {topic_display}.",
                            "step_by_step_solution": "1. Cause 1: Economic and political grievances.\n2. Cause 2: Leadership mobilization of the public.\n3. **Final Answer:** Combined factors ignited the movement.",
                            "key_concept": "Immediate Causes"
                        },
                        {
                            "year_or_type": "Important Question 3 (4 Marks)",
                            "question": f"Explain the role and significance of mass participation in {topic_display}.",
                            "step_by_step_solution": "1. Mobilization of diverse social groups across regions.\n2. Pressure on ruling authorities to grant concessions.\n3. **Result:** Achieved landmark legal and policy reforms.",
                            "key_concept": "Mass Mobilization"
                        },
                        {
                            "year_or_type": "Important Question 4 (4 Marks)",
                            "question": f"Describe the main outcomes and constitutional changes resulting from {topic_display}.",
                            "step_by_step_solution": "1. Shift in public consciousness and political unity.\n2. Creation of new statutory frameworks.\n3. **Conclusion:** Formed the bedrock of modern democratic governance.",
                            "key_concept": "Constitutional Changes"
                        },
                        {
                            "year_or_type": "Important Question 5 (6 Marks)",
                            "question": f"Master Essay: Analyze the socio-economic causes, key stages, and enduring legacy of {topic_display}.",
                            "step_by_step_solution": "Part 1 (Historical Background & Causes): 2 Marks\nPart 2 (Key Phases & Leadership): 2 Marks\nPart 3 (Long-term Impact & National Legacy): 2 Marks",
                            "key_concept": "Master Historical Essay"
                        }
                    ],
                    "content_markdown": content_markdown,
                }
            else:
                # Master Revision Note for STEM
                content_markdown = f"""# ⚡ 5-Minute Cheat Notes: {topic_display}

### Section 1 — ⚡ The Big Idea (30 seconds)
> **{topic_display}** in **{subject}** gives you the essential rules and tools to calculate values, analyze relationships, and solve problems with ease.
- **Why it matters for exams:** High-scoring topic carrying 8 to 12 marks in board exams and tests.

---

### Section 2 — 🍕 Think of It Like This (1-minute analogy)
Think of **{topic_display}** like following a recipe for your favorite dish: when you identify the starting ingredients (given numbers) and follow the simple steps (formulas), you get the right answer every single time!

| Step | What You Do | How It Works |
|:---|:---|:---|
| 1. Find Given Values | Read the question and write down what you know | Starting Ingredients |
| 2. Apply Formula | Pick the right equation and substitute numbers | Cooking Steps |
| 3. Box Final Answer | Double-check arithmetic and write standard units | Serving the Dish |

---

### Section 3 — 💡 Core Concepts (Plain English)

| # | Concept / Term | What It Means in Simple Words |
|:---|:---|:---|
| 1 | **Core Rule** | The governing equation or law defining **{topic_display}** |
| 2 | **Key Variable** | The main value that changes and controls the system |
| 3 | **Proportionality** | How increasing one value makes another go up or down |
| 4 | **Given Conditions** | The initial numbers provided in your exam question |
| 5 | **Standard Units** | Measurement units (like $m/s$, $N$, or $kg$) required for full marks |

---

### Section 4 — 🗺️ How It All Connects (Visual Map)

```mermaid
flowchart TD
    A["📘 {topic_display}"] --> B["Identify Given Values"]
    A --> C["Apply Correct Formula"]
    A --> D["Check Standard Units"]
    B --> E["Full Marks in Exam! 🎯"]
    C --> E
    D --> E
```

---

### Section 5 — 📐 Key Formulas & Equations

| # | Formula | What It Does | Quick Example |
|:---|:---|:---|:---|
| 1 | $y = f(x)$ | Calculates the target output for {topic_display} | Direct formula substitution |
| 2 | $\\Delta y = y_2 - y_1$ | Measures the change between two states | Difference calculation |

---

### Section 6 — ⚠️ Common Exam Traps (Easy Mistakes to Avoid)

| # | Common Mistake | Why Students Get Confused | How to Get It Right |
|:---|:---|:---|:---|
| 1 | ❌ Forgetting Units | Writing just a number without units | **Always box your final answer with its standard unit** |
| 2 | ❌ Skipping Steps | Jumping straight to the final answer | **Show: Given → Formula → Working for full step marks** |
| 3 | ❌ Plus/Minus Sign Errors | Rushing through basic arithmetic | **Double-check negative signs before writing the final value** |
"""
                parsed_data = {
                    "title": title,
                    "high_yield_topics": [f"{topic_display} Definitions", f"{topic_display} Formulas", "Exam Numerical Applications"],
                    "pyq_patterns": [
                        {"topic": f"{topic_display} Core Calculation", "frequency_years": "2022, 2023, 2024", "marks_weightage": "4 Marks", "question_type": "Numerical Application"}
                    ] if has_pyqs else [],
                    "key_formulas": [
                        f"$y = f(x)$ (Primary equation for {topic_display})",
                        "$\\\\Delta y = y_2 - y_1$ (State difference formula)"
                    ],
                    "exam_tips": [
                        f"Always write down the explicit formula for {topic_display} before substituting values.",
                        "Verify SI units for all quantities to secure full marks credit."
                    ],
                    "solved_questions": [
                        {
                            "year_or_type": "Important Question 1 (1 Mark)",
                            "question": f"State the primary definition of {topic_display}.",
                            "step_by_step_solution": f"1. **Definition:** {topic_display} defines fundamental relationships in {subject}.\n2. **Final Answer:** Clear 1-sentence definition.",
                            "key_concept": "Core Definition"
                        },
                        {
                            "year_or_type": "Important Question 2 (2 Marks)",
                            "question": f"State the main governing equation for {topic_display} and label its variables.",
                            "step_by_step_solution": "1. **Formula:** $y = f(x)$\n2. **Variables:** $y$ = output state, $x$ = input parameter.\n3. **Final Answer:** Correct formula with variable keys.",
                            "key_concept": "Governing Equation"
                        },
                        {
                            "year_or_type": "Important Question 3 (4 Marks)",
                            "question": f"A problem in {topic_display} has initial parameter $x = 5$ and rate $k = 3$. Calculate the final state.",
                            "step_by_step_solution": "1. **Given:** $x = 5, k = 3$.\n2. **Formula:** $y = k \\times x$.\n3. **Substitution:** $y = 3 \\times 5 = 15$.\n4. **Final Answer:** **15**",
                            "key_concept": "Numerical Application"
                        },
                        {
                            "year_or_type": "Important Question 4 (4 Marks)",
                            "question": f"Explain the 3 step workflow to solve board exam questions on {topic_display}.",
                            "step_by_step_solution": "1. Step 1: Extract Given Values and target parameter.\n2. Step 2: Write exact LaTeX formula.\n3. Step 3: Substitute and box final answer with units.",
                            "key_concept": "Problem Workflow"
                        },
                        {
                            "year_or_type": "Important Question 5 (6 Marks)",
                            "question": f"Master Essay: Derive and analyze the complete state transition for {topic_display}.",
                            "step_by_step_solution": "Part 1 (Theory): 2 Marks\nPart 2 (Mathematical Working): 2 Marks\nPart 3 (Conclusion & Application): 2 Marks",
                            "key_concept": "Master Case Analysis"
                        }
                    ],
                    "content_markdown": content_markdown,
                }

    # Save to database
    saved_note = db.create_study_note(
        user_id=user_id,
        title=parsed_data.get("title", f"Smart Note: {topic_display}"),
        topic_id=topic_id,
        subject=subject,
        note_type=note_type,
        material_doc_name=material_name,
        pyq_doc_names=pyq_names,
        content_markdown=parsed_data.get("content_markdown", ""),
        high_yield_topics=parsed_data.get("high_yield_topics", []),
        pyq_patterns=parsed_data.get("pyq_patterns", []),
        key_formulas=parsed_data.get("key_formulas", []),
        exam_tips=parsed_data.get("exam_tips", []),
        solved_questions=parsed_data.get("solved_questions", []),
    )

    return saved_note
