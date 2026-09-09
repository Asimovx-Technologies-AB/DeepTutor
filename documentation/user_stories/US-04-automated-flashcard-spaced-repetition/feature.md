# Feature Specification: US-04 Flashcards & Spaced Repetition (Active Recall)

## 📌 Feature Overview
DeepTutor automatically extracts key terms, definitions, and core concepts from uploaded study documents to generate flashcard decks. Students can review cards with an interactive flip interface and rate their recall confidence, driving an adaptive Spaced Repetition algorithm (SM-2 / Leitner model) to schedule card reviews for optimal long-term memory retention.

---

## 👤 User Persona
- **Persona:** Student in high-volume memorization subjects (Medicine, Law, Biology, History, Languages).
- **Need:** Automated flashcard creation so they don't waste hours writing cards manually, paired with intelligent spaced repetition to retain facts long-term.

---

## 📖 User Stories

### Story 4.1: Automated Deck Generation
> **As a** student,  
> **I want to** generate a deck of flashcards automatically from my uploaded PDF,  
> **So that** I have immediate active-recall study materials without manual transcription.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Generating flashcards from study documents
  Given an uploaded document with technical definitions
  When the student selects "Generate Flashcards"
  Then the system extracts key concepts and creates front (prompt/term) and back (definition/formula) pairs
  And saves the new deck under the active subject.
```

### Story 4.2: Spaced Repetition Practice Session
> **As a** student,  
> **I want to** practice flashcards and mark my recall confidence ("Easy", "Good", "Hard", "Again"),  
> **So that** the system schedules harder cards to appear more frequently and easier cards further out.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Reviewing flashcards with spaced repetition
  Given a flashcard deck ready for daily review
  When the student flips a card and rates it as "Hard"
  Then the SM-2 algorithm adjusts the card's ease factor and repetition interval
  And queues the card for review in the next study cycle.
```

---

## 🛠️ Technical Details & API Endpoints

### API Endpoints
* `POST /api/flashcards/generate` - Generates a flashcard deck from document/session chunks.
* `GET /api/flashcards/decks` - Lists user flashcard decks with counts of due and mastered cards.
* `POST /api/flashcards/{card_id}/review` - Records student rating and recalculates next review date.

### Database Impact
* **Tables:** `flashcard_decks`, `flashcards`, `flashcard_reviews` (storing `ease_factor`, `interval_days`, `next_review_at`).
