# Feature Specification: US-01 Document Management & Hybrid RAG Indexing

## 📌 Feature Overview
Students can upload study materials (PDFs, PPTXs, DOCXs, TXT, Markdown) into DeepTutor. The platform calculates SHA-256 content hashes to prevent duplicate ingestion, extracts textual content and key subject topics, indexes the material into a hybrid vector + Full-Text Search (pgvector + PostgreSQL FTS) store, and links documents to study sessions.

---

## 👤 User Persona
- **Persona:** University Student / Self-Directed Learner
- **Need:** Wants to quickly upload lecture notes, slides, and textbooks, and have them organized into subjects and topics ready for instant AI tutoring.

---

## 📖 User Stories

### Story 1.1: Document Upload & Deduplication
> **As a** student,  
> **I want to** upload single or multiple study documents to my subject library,  
> **So that** I don't waste storage or compute if I re-upload the same file twice.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Uploading a new study document
  Given an authenticated user on the Materials/Subjects page
  When the user uploads a valid PDF or PPTX file
  Then the system computes its SHA-256 hash
  And stores the file in user-isolated storage
  And creates a record in `session_documents` with document metadata.

Scenario: Uploading an identical duplicate file
  Given a user has already uploaded "Calculus_Notes.pdf"
  When the user attempts to upload the exact same file content
  Then the system detects the existing SHA-256 hash
  And links the existing document record without re-indexing chunks.
```

### Story 1.2: Automatic Topic & Chunk Extraction
> **As a** student,  
> **I want** the system to automatically break documents into semantic chunks and identify key topics,  
> **So that** the AI can ground its tutoring responses in specific sections of my notes.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Text chunking and Hybrid Indexing
  Given a successfully uploaded document
  When the background ingestion pipeline runs
  Then the document is split into overlapping chunks (e.g. 500-1000 tokens)
  And embeddings are computed and stored in pgvector
  And PostgreSQL Full-Text Search tsvectors are generated
  And top subject topics are extracted and associated with the session.
```

### Story 1.3: Document Management & Session Linking
> **As a** student,  
> **I want to** select one or more documents from my library and launch a dedicated study room,  
> **So that** my tutor focuses specifically on the selected material.

#### Acceptance Criteria (Gherkin):
```gherkin
Scenario: Launching a multi-material study room
  Given a user selects 2 documents in the Material Session Modal
  When the user clicks "Start Study Session"
  Then a new study session is created
  And the 2 documents are linked in `session_documents_association`
  And the user is redirected to the Interactive Learn Page.
```

---

## 🛠️ Technical Details & API Endpoints

### API Endpoints
* `POST /api/documents/upload` - Uploads document with multipart file, subject, and session metadata.
* `GET /api/documents/` - Lists all user-owned documents with indexing status and topic counts.
* `DELETE /api/documents/{doc_id}` - Safely deletes document and cascades chunk removal with user authorization check.
* `POST /api/documents/session-materials` - Fetches all materials linked to an active session.

### Database Impact
* **Tables:** `session_documents`, `session_document_chunks`, `session_topic_registry`.
* **Hybrid Search:** PostgreSQL `pgvector` embedding table + `to_tsvector('english', chunk_text)` FTS index.
