# Feature Specification: US-02 Interactive Learning Room & Multi-Modal Tutoring

## 📌 Feature Overview
The Interactive Learn Room is the core study environment in DeepTutor. It features real-time conversational AI grounded in uploaded document context using Hybrid RAG (pgvector + FTS). It supports three distinct learning modes (**Normal Mode**, **Teacher / Socratic Mode**, and **Exam Preparation Mode**), audio voice synthesis (TTS), rich LaTeX math rendering, and dynamic Mermaid diagram generation.

---

## 👤 User Persona
- **Persona:** Student preparing for exams or mastering complex conceptual material.
- **Need:** An adaptive tutor that can explain concepts simply, ask guided questions in teacher mode, test under pressure in exam mode, and display formulas and architecture diagrams clearly.

---

## 📖 User Stories

### Story 2.1: Multi-Turn RAG Chat with Rich Media
> **As a** student,  
> **I want to** ask questions about my uploaded documents and receive formatted answers with formulas and diagrams,  
> **So that** I can understand difficult technical concepts visually and mathematically.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Querying study materials
  Given an active study session with indexed lecture slides
  When the student types a question in the chat input
  Then the system executes hybrid search (pgvector embedding + FTS RRF fusion)
  And feeds relevant context chunks into the LLM
  And streams the response with rendered KaTeX formulas ($E=mc^2$) and Mermaid diagrams.
```

### Story 2.2: Socratic Teacher Mode
> **As a** student,  
> **I want** the tutor to act as a Socratic teacher who guides me with leading questions rather than giving immediate answers,  
> **So that** I develop deeper critical thinking and problem-solving skills.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Engaging in Teacher Mode
  Given the student selects "Teacher Mode" from the mode toggle
  When the student asks "How do B-Trees balance?"
  Then the AI responds with guiding questions prompting the student to explain node splitting
  And evaluates the student's answer step-by-step.
```

### Story 2.3: Strict Exam Mode
> **As a** student,  
> **I want** an intensive Exam Mode that simulates test conditions,  
> **So that** I can practice answering timed, rigorous questions under exam constraints.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Engaging in Exam Mode
  Given the student selects "Exam Mode"
  When the study session begins
  Then hints are disabled, timed prompts appear, and the AI evaluates answers with grading rubrics.
```

### Story 2.4: Session Isolation Across Modes
> **As a** student,  
> **I want** switching modes or starting a new session to completely reset state buffers,  
> **So that** messages or artifacts from previous sessions do not leak into my new session.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Clean Mode Reset
  Given an active session with chat history in Normal mode
  When the student clicks "New Session" or switches to Teacher/Exam mode
  Then the frontend invokes `resetModeStates()`
  And previous messages, diagrams, and temporary buffers are flushed immediately.
```

---

## 🛠️ Technical Details & API Endpoints

### API Endpoints
* `POST /api/study/chat` - Submits student message with session context, retrieves RAG chunks, and returns AI answer with citation metadata.
* `POST /api/study/voice` - Generates TTS audio speech for AI responses.
* `GET /api/study/session/{session_id}/history` - Loads historical dialogue for the session.

### Frontend Components
* `frontend/src/pages/LearnPage.tsx` - Main workspace with tabbed views for Chat, Mindmap, Whiteboard, and Code Sandbox.
* `frontend/src/components/SessionLoadingAnimation.tsx` - Smooth loading transitions during RAG retrieval and indexing.
