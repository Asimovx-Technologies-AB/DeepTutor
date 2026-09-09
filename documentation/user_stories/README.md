# DeepTutor User Stories Index

This directory contains the user stories and feature specifications for the **DeepTutor** intelligent learning platform. Each folder represents an independent user story / epic and contains a comprehensive feature markdown file with persona definition, user stories (Given-When-Then acceptance criteria), technical architecture, API interactions, and security requirements.

---

## 📚 User Stories Directory

| ID | Feature Name | Epic / Domain | Key Capabilities |
| :--- | :--- | :--- | :--- |
| **[US-01](./US-01-document-management-and-indexing/feature.md)** | **Document Management & Ingestion** | Ingestion & Hybrid RAG | Multi-file upload, SHA256 deduplication, chunking, topic extraction, pgvector + FTS indexing. |
| **[US-02](./US-02-interactive-learning-room-modes/feature.md)** | **Interactive Learning Room** | AI Tutoring & Modes | Multi-turn chat, Socratic Teacher mode, Strict Exam mode, LaTeX/Mermaid rendering, Audio TTS. |
| **[US-03](./US-03-ai-exam-and-quiz-generation/feature.md)** | **AI Quiz & Assessment Engine** | Knowledge Testing | Dynamic question generation from uploaded notes, multi-choice evaluation, scoring, detailed explanations. |
| **[US-04](./US-04-automated-flashcard-spaced-repetition/feature.md)** | **Flashcards & Active Recall** | Memory Retention | AI flashcard extraction, Spaced Repetition (SM-2 algorithm), mastery ratings, deck review. |
| **[US-05](./US-05-dynamic-study-plan-roadmap/feature.md)** | **Dynamic Study Plan & Roadmap** | Personalized Learning | Syllabus-driven milestones, daily goal scheduler, task progress tracking. |
| **[US-06](./US-06-student-dashboard-and-analytics/feature.md)** | **Learning Analytics & Dashboard** | Progress Tracking | Active time tracking heartbeat, subject mastery radar, activity timeline, study statistics. |
| **[US-07](./US-07-mcp-sandboxed-code-and-math-solver/feature.md)** | **MCP Code Sandbox & Math Solver** | Agentic Tools | AST-sandboxed Python runtime, SymPy algebraic equation solver, safe tool execution. |
| **[US-08](./US-08-authentication-security-and-isolation/feature.md)** | **Authentication & Multi-Tenant Security** | Platform Security | JWT auth, isolated per-user sessions, fail-closed access control, PostgreSQL data integrity. |

---

## 🎯 User Story Structure Standard
Every feature file follows the Agile specification standard:
1. **User Persona & Context**
2. **User Stories (`As a... I want to... So that...`)**
3. **Acceptance Criteria (Gherkin format: `Given-When-Then`)**
4. **API Endpoints & Contracts**
5. **Database & Persistence Impact**
6. **Security & Non-Functional Requirements**
