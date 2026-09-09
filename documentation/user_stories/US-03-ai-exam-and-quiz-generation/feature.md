# Feature Specification: US-03 AI Exam & Quiz Generation Engine

## 📌 Feature Overview
The Assessment Engine allows students to generate customized practice quizzes and mock exams dynamically from their uploaded notes and study sessions. It supports customizable difficulty levels (Easy, Medium, Hard), question types (Multiple Choice, True/False, Short Answer), instant grading, and detailed explanations for both correct and incorrect choices.

---

## 👤 User Persona
- **Persona:** Student preparing for midterms, finals, or standardized certifications.
- **Need:** Self-assessment tools grounded in their specific course material to identify knowledge gaps before taking actual exams.

---

## 📖 User Stories

### Story 3.1: Dynamic Quiz Generation
> **As a** student,  
> **I want to** generate a 5 to 20 question quiz from my uploaded lecture slides,  
> **So that** I can test my comprehension of specific topics.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Generating a topic-specific quiz
  Given an authenticated user with uploaded materials for "Linear Algebra"
  When the user requests a 10-question quiz on "Eigenvalues" with "Medium" difficulty
  Then the system queries RAG vector store for eigenvalue contexts
  And the LLM generates structured JSON containing questions, options, correct answers, and explanations
  And saves the quiz to the user's assessment history.
```

### Story 3.2: Interactive Quiz Taking & Scoring
> **As a** student,  
> **I want to** select answers, submit my quiz, and receive an instant breakdown of my score and errors,  
> **So that** I understand why an answer was wrong and reinforce correct concepts.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Submitting quiz answers
  Given a generated quiz in progress
  When the user selects answers for all questions and clicks "Submit"
  Then the system grades each question
  And highlights correct answers in green and incorrect in red
  And displays step-by-step explanations citing the source document chunk
  And records the final score in `user_progress` and the dashboard stats.
```

---

## 🛠️ Technical Details & API Endpoints

### API Endpoints
* `POST /api/quiz/generate` - Generates quiz questions from document context and difficulty parameters.
* `POST /api/quiz/submit` - Submits student answers, calculates accuracy score, and records attempt history.
* `GET /api/quiz/history` - Returns previous quiz attempts, timestamps, and scores.

### Database Impact
* **Tables:** `quizzes`, `quiz_questions`, `quiz_attempts`, `user_progress`.
