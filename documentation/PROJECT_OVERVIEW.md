# Deep Tutor MVP

## Overview

Deep Tutor is an AI-powered personalized tutoring platform that combines local LLM intelligence, document retrieval, and knowledge graph reasoning. Students can upload PDF study material, ask questions, generate practice quizzes and flashcards, and track progress through a dynamic learning dashboard.

The platform is built as a modern full-stack application with:
- **Backend**: FastAPI, SQLAlchemy, SQLite, ChromaDB, NetworkX, and Ollama for local language model execution.
- **Frontend**: React + Vite with TypeScript, TailwindCSS, Framer Motion, and Recharts.

## Core Capabilities

- **GraphRAG-powered chat**: Uses uploaded PDF content and a knowledge graph to answer questions accurately.
- **Session-scoped generation**: Quiz and flashcard content are generated based on the current user's uploaded PDF session.
- **PDF upload and indexing**: Supports PDF uploads, extracts text, and stores embedded chunks in per-user ChromaDB collections.
- **AI Quiz Engine**: Generates multiple-choice quizzes directly from uploaded PDF context.
- **Flashcard Generator**: Produces study flashcards from document content.
- **Study Plan Generator**: Creates a structured day-by-day roadmap for learning from uploaded material.
- **Progress analytics**: Tracks quiz attempts, scores, and learning sessions over time.

## Architecture

The system is split into three main layers:

1. **Frontend**
   - React + Vite application provides interactive UI for chat, quizzes, dashboards, and uploads.
   - Uses `axios` for API communication and `zustand` for lightweight state management.
   - `react-router-dom` handles app navigation.

2. **Backend**
   - FastAPI exposes REST endpoints for authentication, document upload, quiz generation, flashcards, progress, and chat.
   - Database models are managed by SQLAlchemy and stored in SQLite.
   - Document processing and RAG indexing happen in the backend.

3. **Local AI Layer**
   - Ollama runs a local LLM model (configured as `llama3.2` by default).
   - Embeddings use `nomic-embed-text`.
   - ChromaDB stores vector embeddings for document chunks, and NetworkX builds a knowledge graph.

## Data Flow

- Users upload PDF documents through the frontend.
- The backend saves uploads under `uploads/{user_id}/{topic_id}`.
- Documents are processed into text chunks and indexed into ChromaDB under a namespaced collection.
- The RAG pipeline retrieves relevant chunks for chat and quiz generation.
- Quiz content is generated from session-specific or topic-specific document context.

## Project Structure

```
Deep_Tutor_MVP/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── documents.py
│   │   │   ├── flashcards.py
│   │   │   ├── quiz.py
│   │   │   ├── progress.py
│   │   │   ├── study_plan.py
│   │   │   └── leaderboard.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   └── models.py
│   │   ├── rag/
│   │   │   ├── quiz_generator.py
│   │   │   ├── flashcard_generator.py
│   │   │   ├── graph_rag.py
│   │   │   ├── vector_store.py
│   │   │   ├── document_processor.py
│   │   │   └── graph_store.py
│   │   ├── main.py
│   │   ├── mcp_server.py
│   │   └── ...
│   ├── requirements.txt
│   └── start.bat
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   ├── services/
│   │   └── stores/
│   ├── package.json
│   ├── tsconfig.json
│   └── index.html
├── graphs_data/
├── chroma_data/
├── uploads/
├── README.md
└── implementation_plan.md
```

## Backend Configuration

Primary configuration values are stored in `backend/app/core/config.py`.
Key settings include:
- `APP_NAME`, `APP_VERSION`, `DEBUG`
- `DATABASE_URL` for SQLite
- `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`
- `CHROMA_PERSIST_DIR`, `GRAPH_DATA_DIR`
- `UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`
- RAG-specific tuning values like `CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K_CHUNKS`, and `GRAPH_HOP_DEPTH`

## Setup Instructions

### Backend

1. Open a terminal and navigate to `backend`.
2. Create a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the backend server:

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend

1. Open another terminal and navigate to `frontend`.
2. Install dependencies:

```bash
npm install
```

3. Start the frontend development server:

```bash
npm run dev
```

4. Open the browser to the address shown by Vite, typically `http://localhost:5173`.

## Usage Guide

### 1. Upload PDF
- Click the PDF upload button in the chat page.
- The file is saved to `uploads/{user_id}/{topic_id}/` and indexed in ChromaDB.
- The platform begins GraphRAG indexing in the background.

### 2. Ask Questions
- Enter study questions in the chat input.
- The backend retrieves relevant PDF context and responds using the local LLM.

### 3. Generate Quizzes
- Open the quiz module or quiz overlay.
- Select whether to generate a quiz for the entire PDF or a specific concept.
- The system will generate a quiz based on your uploaded PDF session content.

### 4. Create Flashcards
- Use the flashcard generator to produce learner flashcards from document context.

### 5. Study Plan
- Supply a target completion date.
- The backend builds a custom study schedule from the uploaded material.

## Important Behavior

- Document content is indexed into per-user, per-topic ChromaDB collections.
- Quiz and flashcard generation are designed to use uploaded PDF session data rather than global or unrelated documents.
- If direct PDF text cannot be found, the backend falls back to topic-specific or general vector store data.

## Local AI Requirements

The backend expects a locally running Ollama instance. Confirm the following:
- `Ollama` is installed and running.
- The configured model is available (default `llama3.2`).
- Embedding model `nomic-embed-text` is accessible.

## Recommended Enhancements

- Add session-specific guards so quiz generation only proceeds when a session has indexed PDF content.
- Improve uploaded document metadata tagging for page-aware quiz/exam generation.
- Add end-to-end tests for quiz and flashcard generation flows.
- Support additional file types and scanned-document OCR.

## Notes

This project is an MVP for a privacy-first local AI tutor. It emphasizes:
- local model execution via Ollama
- document-grounded generation
- per-user learning sessions
- a blended vector search + knowledge graph approach

---

For more details, review `README.md` and `implementation_plan.md` in the repository root.
