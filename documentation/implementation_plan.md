# 🎓 Deep Tutor MVP — AI Tutor Platform

## Overview

An AI-powered personalized tutor platform that uses a **local LLM** (via Ollama) to deliver intelligent, context-aware tutoring sessions. Students can ask questions, receive explanations, take quizzes, and track their learning progress — all powered by a locally running LLM for privacy and offline capability.

---

## 🏗️ Architecture Diagram

```mermaid
graph TB
    subgraph CLIENT["🖥️ Frontend (React + Vite)"]
        UI["Chat UI / Dashboard"]
        AUTH["Auth Pages (Login/Register)"]
        QUIZ["Quiz Module"]
        PROGRESS["Progress Tracker"]
    end

    subgraph BACKEND["⚙️ Backend (FastAPI / Python)"]
        API["REST API Layer"]
        AUTH_SVC["Auth Service (JWT)"]
        TUTOR_SVC["Tutor Service"]
        QUIZ_SVC["Quiz Service"]
        PROG_SVC["Progress Service"]
        RAG["RAG Pipeline (LangChain)"]
    end

    subgraph LOCAL_AI["🤖 Local AI Layer"]
        OLLAMA["Ollama Server"]
        LLM["Local LLM\n(Llama3 / Mistral / Gemma)"]
        EMBED["Embedding Model\n(nomic-embed-text)"]
    end

    subgraph DATA["🗄️ Data Layer"]
        DB[("PostgreSQL\nMain Database")]
        VECTOR[("ChromaDB\nVector Store")]
        CACHE[("Redis\nSession Cache")]
    end

    subgraph STORAGE["📁 Storage"]
        FILES["File Store\n(PDFs, Docs)"]
    end

    UI --> API
    AUTH --> API
    QUIZ --> API
    PROGRESS --> API

    API --> AUTH_SVC
    API --> TUTOR_SVC
    API --> QUIZ_SVC
    API --> PROG_SVC

    TUTOR_SVC --> RAG
    RAG --> VECTOR
    RAG --> OLLAMA
    OLLAMA --> LLM
    OLLAMA --> EMBED

    AUTH_SVC --> DB
    TUTOR_SVC --> DB
    QUIZ_SVC --> DB
    PROG_SVC --> DB

    TUTOR_SVC --> CACHE
    FILES --> RAG
```

---

## 📊 ER Diagram

```mermaid
erDiagram
    USER {
        uuid id PK
        string username
        string email
        string password_hash
        string role
        timestamp created_at
        timestamp updated_at
    }

    SUBJECT {
        uuid id PK
        string name
        string description
        string icon
        timestamp created_at
    }

    TOPIC {
        uuid id PK
        uuid subject_id FK
        string title
        string description
        int order_index
        string difficulty_level
        timestamp created_at
    }

    DOCUMENT {
        uuid id PK
        uuid topic_id FK
        uuid uploaded_by FK
        string file_name
        string file_path
        string file_type
        string vector_collection_id
        timestamp created_at
    }

    CHAT_SESSION {
        uuid id PK
        uuid user_id FK
        uuid topic_id FK
        string session_title
        timestamp started_at
        timestamp ended_at
    }

    MESSAGE {
        uuid id PK
        uuid session_id FK
        string role
        text content
        json metadata
        timestamp created_at
    }

    QUIZ {
        uuid id PK
        uuid topic_id FK
        string title
        string difficulty
        int time_limit_mins
        timestamp created_at
    }

    QUESTION {
        uuid id PK
        uuid quiz_id FK
        text question_text
        string question_type
        json options
        string correct_answer
        string explanation
    }

    QUIZ_ATTEMPT {
        uuid id PK
        uuid user_id FK
        uuid quiz_id FK
        int score
        int total_questions
        float percentage
        json answers
        timestamp attempted_at
    }

    USER_PROGRESS {
        uuid id PK
        uuid user_id FK
        uuid topic_id FK
        int messages_count
        int quizzes_taken
        float avg_quiz_score
        string mastery_level
        timestamp last_active
    }

    USER ||--o{ CHAT_SESSION : "has"
    USER ||--o{ QUIZ_ATTEMPT : "attempts"
    USER ||--o{ USER_PROGRESS : "tracks"
    SUBJECT ||--o{ TOPIC : "contains"
    TOPIC ||--o{ CHAT_SESSION : "belongs to"
    TOPIC ||--o{ QUIZ : "has"
    TOPIC ||--o{ DOCUMENT : "has"
    TOPIC ||--o{ USER_PROGRESS : "tracked in"
    QUIZ ||--o{ QUESTION : "contains"
    QUIZ ||--o{ QUIZ_ATTEMPT : "attempted via"
    CHAT_SESSION ||--o{ MESSAGE : "contains"
    USER ||--o{ DOCUMENT : "uploads"
```

---

## 🛠️ Tech Stack Recommendations

### 🖥️ Frontend
| Layer | Technology | Why |
|---|---|---|
| Framework | **React + Vite** | Fast dev server, HMR, modern DX |
| Styling | **Tailwind CSS** | Rapid UI, utility-first, great defaults |
| State Mgmt | **Zustand** | Lightweight, simple, no boilerplate |
| Chat UI | **React Markdown + Highlight.js** | Render LLM markdown responses |
| HTTP Client | **Axios + React Query** | Caching, retries, background refetch |
| Routing | **React Router v6** | Industry standard SPA routing |
| Auth | **JWT stored in httpOnly cookie** | Secure token management |
| Charts | **Recharts** | Progress/analytics visualizations |

### ⚙️ Backend
| Layer | Technology | Why |
|---|---|---|
| Framework | **FastAPI (Python)** | Async support, auto docs, fast |
| Auth | **python-jose + passlib** | JWT + bcrypt hashing |
| ORM | **SQLAlchemy + Alembic** | Type-safe queries + migrations |
| LLM Orchestration | **LangChain** | RAG pipelines, memory, chains |
| Streaming | **Server-Sent Events (SSE)** | Real-time token streaming from LLM |
| Task Queue | **Celery + Redis** | Async document processing |
| Validation | **Pydantic v2** | Data models and validation |

### 🤖 Local AI Layer
| Component | Technology | Why |
|---|---|---|
| LLM Server | **Ollama** | Easy local LLM management |
| Chat Model | **Llama 3.1 8B / Mistral 7B** | Best quality/speed tradeoff for MVP |
| Embeddings | **nomic-embed-text** | Fast, high-quality local embeddings |
| Vector Store | **ChromaDB** | Local, file-based, easy to start |
| RAG Framework | **LangChain** | Retrieval-augmented generation |

### 🗄️ Database & Storage
| Layer | Technology | Why |
|---|---|---|
| Primary DB | **PostgreSQL** | Relational, reliable, JSON support |
| Vector DB | **ChromaDB** | Local vector search, no extra infra |
| Cache | **Redis** | Session store, rate limiting |
| File Storage | **Local filesystem / MinIO** | PDF uploads, documents |

### 🚀 DevOps (MVP)
| Tool | Purpose |
|---|---|
| **Docker + Docker Compose** | Run everything with one command |
| **Nginx** | Reverse proxy for Frontend + Backend |
| **Alembic** | DB schema migrations |

---

## 🗺️ MVP Feature Scope

### ✅ MVP Phase 1 (Build First)
- [x] User Registration & Login (JWT)
- [x] Subject & Topic Browsing
- [x] AI Chat Session with local LLM (streaming)
- [x] Document Upload + RAG (ask questions about uploaded PDFs)
- [x] Auto-generated Quizzes from LLM
- [x] Quiz Attempt & Scoring
- [x] Basic Progress Dashboard

### 🔜 Phase 2 (Post-MVP)
- [ ] Spaced Repetition System (SRS)
- [ ] Voice Input/Output
- [ ] Collaborative Study Rooms
- [ ] LLM Model switcher in UI
- [ ] Student analytics for teachers

---

## 📁 Project Structure

```
Deep_Tutor_MVP/
├── frontend/                  # React + Vite app
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Route-level pages
│   │   ├── stores/            # Zustand state stores
│   │   ├── services/          # API service functions
│   │   └── hooks/             # Custom React hooks
│   └── package.json
│
├── backend/                   # FastAPI application
│   ├── app/
│   │   ├── api/               # Route handlers
│   │   ├── services/          # Business logic
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── core/              # Config, auth, db
│   │   └── rag/               # LangChain RAG pipeline
│   ├── alembic/               # DB migrations
│   └── requirements.txt
│
├── docker-compose.yml         # Orchestrate all services
└── README.md
```

---

## 🔄 Data Flow — Chat Session

```mermaid
sequenceDiagram
    participant U as User Browser
    participant API as FastAPI Backend
    participant RAG as RAG Pipeline
    participant VEC as ChromaDB
    participant OL as Ollama (Local LLM)
    participant DB as PostgreSQL

    U->>API: POST /chat/message {session_id, content}
    API->>DB: Save user message
    API->>RAG: process(user_message, session_id)
    RAG->>VEC: similarity_search(user_message)
    VEC-->>RAG: relevant_docs[]
    RAG->>DB: fetch last N messages (memory)
    RAG->>OL: chat(system_prompt + context + history + query)
    OL-->>API: stream tokens (SSE)
    API-->>U: stream tokens (SSE)
    API->>DB: Save assistant message (after stream complete)
```

---

## ⚠️ Open Questions

> [!IMPORTANT]
> **Q1**: Should the MVP support **multiple subjects** (Math, Science, History) from day 1, or start with a single configurable subject?

> [!IMPORTANT]
> **Q2**: Do you want **teacher/admin roles** in the MVP, or just student accounts for now?

> [!IMPORTANT]
> **Q3**: Which local LLM would you prefer? Options:
> - **Llama 3.1 8B** — Great all-rounder, needs ~8GB RAM
> - **Mistral 7B** — Fast and instruction-tuned, needs ~6GB RAM
> - **Gemma 2 9B** — Google's model, excellent reasoning

> [!NOTE]
> **Q4**: Should we start building the **frontend first** (UI demo), **backend first** (API + LLM), or use **Docker Compose** to wire everything up together?
