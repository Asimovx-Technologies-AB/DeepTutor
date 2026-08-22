# 🛠️ DeepTutor — Comprehensive Tech Stack & System Architecture

> **DeepTutor** is a privacy-first, local & multi-provider AI-powered personalized tutoring platform. It integrates a 4-Stage RAG (Retrieval-Augmented Generation) Pipeline, GraphRAG knowledge structures, dynamic quiz & flashcard generation, interactive student analytics, and Model Context Protocol (MCP) capabilities.

---

## 📐 1. System Architecture Overview

DeepTutor follows a decoupled client-server architecture designed for high scalability, offline capabilities, and local-first execution with fallback options for cloud-based providers.

```mermaid
graph TB
    subgraph CLIENT["🖥️ Frontend Layer (React 19 + Vite 8)"]
        UI["React SPA UI Components"]
        STATE["Zustand State Stores"]
        QUERY["TanStack React Query"]
        ROUTER["React Router v7"]
        RENDER["Markdown / KaTeX / Mermaid / Recharts"]
    end

    subgraph BACKEND["⚙️ Backend Layer (FastAPI / Uvicorn)"]
        API["FastAPI REST API"]
        AUTH["JWT Security & Auth"]
        SERVICES["Core Domain Services"]
        MCP_MGR["FastMCP Server & Client Manager"]
    end

    subgraph RAG_ENGINE["🧠 4-Stage RAG & Intelligence Pipeline"]
        STAGE1["Stage 1: PyMuPDF / IBM Docling + Semantic Chunker"]
        STAGE2["Stage 2: Ollama / OpenAI / Gemini Embeddings + TTL LRU Cache"]
        STAGE3["Stage 3: FAISS HNSW Vector Store + LightRAG Graph KV Store"]
        STAGE4["Stage 4: BM25 Hybrid Retrieval + Reranker + Hallucination Guard"]
    end

    subgraph AI_PROVIDERS["🤖 AI Models & Runtime"]
        OLLAMA["Local Ollama (Llama 3.2, Mistral, Gemma 2, nomic-embed-text)"]
        GEMINI["Google Gemini API (text-embedding-004, Gemini Pro)"]
        OPENAI["OpenAI API (text-embedding-3-small/large)"]
    end

    subgraph STORAGE["🗄️ Database & Storage Layer"]
        REL_DB[("Neon PostgreSQL (Cloud) / SQLite (Local)")]
        VEC_DB[("FAISS / Pinecone Serverless / ChromaDB")]
        GRAPH_DB[("LightRAG JSON-KV / NetworkX")]
        FILES[("Local Disk Uploads / AWS S3 Storage")]
        CACHE[("Embedding & Query LRU Cache")]
    end

    subgraph MCP["🔌 Model Context Protocol (MCP)"]
        MCP_SERVER["FastMCP Stdio/SSE Server"]
        EXT_CLIENTS["External Clients (Cursor IDE, Claude Desktop, VS Code)"]
    end

    UI --> API
    STATE --> API
    QUERY --> API

    API --> AUTH
    API --> SERVICES
    API --> MCP_MGR

    SERVICES --> RAG_ENGINE
    MCP_MGR --> RAG_ENGINE
    MCP_SERVER <--> EXT_CLIENTS
    MCP_SERVER <--> RAG_ENGINE

    STAGE1 --> FILES
    STAGE2 --> AI_PROVIDERS
    STAGE2 --> CACHE
    STAGE3 --> VEC_DB
    STAGE3 --> GRAPH_DB
    STAGE4 --> AI_PROVIDERS

    AUTH --> REL_DB
    SERVICES --> REL_DB
```

---

## 🧰 2. Complete Technology Stack

### 🖥️ Frontend Architecture

| Category | Technology | Version | Purpose & Description |
|---|---|---|---|
| **Core Framework** | React | `^19.2.8` | Declarative UI component tree structure with high-concurrency features |
| **Build Tooling** | Vite | `^8.2.0` | Ultra-fast HMR module bundling and TypeScript compilation |
| **Language** | TypeScript | `~6.0.2` | End-to-end static type safety and interface definitions |
| **Styling** | Tailwind CSS | `^4.3.3` | Utility-first CSS engine with `@tailwindcss/vite` integration |
| **Typography** | Google Fonts | `^5.3.0` | Fonts (`@fontsource/fredoka`, `@fontsource/nunito`, `@fontsource/outfit`) |
| **Icons** | Lucide React | `^1.28.0` | Clean vector iconography set |
| **State Management** | Zustand | `^5.0.14` | Lightweight state containers (`authStore`, `chatStore`, `subjectStore`) |
| **Data Fetching** | TanStack Query + Axios | `^5.101.4` / `^1.19.0` | Declarative async state caching, auto-refetching, and HTTP requests |
| **Routing** | React Router DOM | `^7.18.2` | Single Page Application (SPA) client-side routing |
| **Animations** | Framer Motion | `^12.43.0` | Micro-animations, page transitions, interactive UI gestures |
| **Visual Effects** | Canvas Confetti | `^1.9.4` | Gamified reward animations for quiz completion |
| **Data Visualization** | Recharts | `^3.10.1` | Analytics charts, performance breakdown, mastery metrics |
| **Markdown Parsing** | React Markdown + GFM | `^10.1.0` / `^4.0.1` | Rendering rich formatted responses from LLM |
| **Formula Rendering** | KaTeX + Rehype/Remark | `^0.18.4` | High-fidelity mathematical expression rendering (`$E=mc^2$`) |
| **Code Highlighting** | Highlight.js | `^11.11.1` | Syntax highlighting for code snippets in chat and notes |
| **Diagrams & Graphs** | Mermaid | `^11.17.0` | Dynamic sequence charts, flowcharts, and 3D graph visualizers |
| **Linter** | Oxlint | `^1.75.0` | Fast Rust-based JavaScript/TypeScript linter |

---

### ⚙️ Backend Architecture

| Category | Technology | Version | Purpose & Description |
|---|---|---|---|
| **Web Framework** | FastAPI | `>=0.111.0` | Asynchronous high-performance Python web application framework |
| **ASGI Server** | Uvicorn | `>=0.30.0` | Standard ASGI server implementation with live reloading capabilities |
| **Database ORM** | SQLAlchemy | `>=2.0.0` | Modern Python SQL toolkit and Object Relational Mapper |
| **Data Validation** | Pydantic & Settings | `>=2.7.0` | Environment validation and strongly typed API request/response schemas |
| **Authentication** | Passlib & Python-JOSE | `>=1.7.4` / `>=3.3.0` | Bcrypt password hashing and JWT token processing |
| **Async Drivers** | AIOSQLite / Psycopg2 | `>=0.20.0` / `>=2.9.9` | Asynchronous SQLite driver & PostgreSQL binary driver |
| **HTTP Client** | HTTPX & AIOFiles | `>=0.27.0` / `>=23.2.1` | Non-blocking HTTP client and async filesystem operations |
| **Retry & Utilities** | Tenacity & Python-Dotenv | `>=8.3.0` / `>=1.0.0` | Execution retries with exponential backoff and env management |
| **Cloud Storage SDK** | Boto3 | `>=1.34.0` | AWS S3 object storage connector for document backups |

---

## 🔬 3. The 4-Stage Advanced RAG Pipeline Architecture

DeepTutor features a multi-tiered Retrieval-Augmented Generation (RAG) framework optimized for structured academic textbooks and complex documents.

```mermaid
flowchart LR
    subgraph STAGE1["Stage 1: Document Processing"]
        Doc[Uploaded PDF] --> PyMuPDF[PyMuPDF / fitz]
        Doc --> Docling[IBM Docling Parser]
        PyMuPDF --> Chunker[Semantic Chunker]
        Docling --> Chunker
        Chunker --> Trees[Hierarchical Section Trees]
    end

    subgraph STAGE2["Stage 2: Multi-Provider Embeddings"]
        Trees --> Embedder{Embedding Provider}
        Embedder -->|Local| OllamaEmbed[Ollama nomic-embed-text]
        Embedder -->|Cloud| OpenAIEmbed[OpenAI text-embedding-3]
        Embedder -->|Cloud| GeminiEmbed[Google text-embedding-004]
        OllamaEmbed --> Cache[TTL-Aware LRU Cache]
    end

    subgraph STAGE3["Stage 3: Dual Storage Indexing"]
        Cache --> FAISS[FAISS HNSW Vector Store]
        Cache --> Pinecone[Pinecone Serverless]
        Trees --> LightRAG[LightRAG JSON-KV Graph Store]
    end

    subgraph STAGE4["Stage 4: Hybrid Search & Generation"]
        Query[User Question] --> BM25[BM25+ Sparse Search]
        Query --> Dense[FAISS Dense Search]
        Query --> GraphHop[LightRAG Graph Traversal]
        BM25 --> Reranker[Cosine Similarity & Score Reranker]
        Dense --> Reranker
        GraphHop --> Reranker
        Reranker --> Guard[Hallucination Guard]
        Guard --> LLM[Local / Cloud LLM Output]
    end
```

### Stage 1: Document Parsing & Semantic Chunking
- **Parsers**:
  - **PyMuPDF (`fitz`)**: Primary high-speed text and layout extractor.
  - **IBM Docling (`docling`)**: Deep structural parser for multi-column academic papers, complex tabular data, formula extraction, and OCR.
  - **Fallbacks**: `pdfplumber`, `pypdf`, `pytesseract`, `easyocr`, `python-docx`, `openpyxl`, `python-pptx`, `beautifulsoup4`.
- **Semantic Chunker**: Dynamically partitions documents based on heading hierarchy (`section_tree.py`) with configurable word windows (`CHUNK_MIN_WORDS` to `CHUNK_MAX_WORDS`).

### Stage 2: Multi-Provider Embeddings & Caching
- **Providers**:
  - **Local**: Ollama `nomic-embed-text` (768 dimensions).
  - **OpenAI**: `text-embedding-3-small` / `text-embedding-3-large`.
  - **Google Gemini**: `text-embedding-004`.
- **Caching**: Memory-resident TTL-aware LRU cache (`cachetools`) preventing duplicate vector computations for frequent queries and document re-indexing.

### Stage 3: Dual Storage Indexing (Vector + Knowledge Graph)
- **Vector Store Backends**:
  - **FAISS HNSW** (`faiss-cpu`): Primary local vector index for high-speed nearest-neighbor retrieval.
  - **Pinecone Serverless**: Cloud-native scalable vector repository fallback.
  - **ChromaDB**: Legacy persistent file vector storage support.
- **Graph RAG**:
  - **LightRAG**: Entity-relation extraction indexed in JSON-KV structures (`graph_kv.py`).
  - **NetworkX**: Dynamic entity traversal and graph algorithms powering 3D knowledge map rendering.

### Stage 4: Advanced Hybrid Retrieval & Generation
- **Hybrid Retrieval**: Combines BM25+ sparse lexical matching, FAISS dense vector search, and multi-hop knowledge graph neighborhood traversals.
- **Reranking**: `scikit-learn` cosine similarity utilities and relevance scoring filters out out-of-context chunks.
- **Hallucination Guard**: `hallucination_guard.py` evaluates source context alignment before dispatching prompts to Ollama (`llama3.2`, `mistral`, `gemma2`) or Gemini API.

---

## 🗄️ 4. Data Layer & Database ER Schema

DeepTutor uses a flexible database adapter pattern supporting both cloud **Neon PostgreSQL** and local **SQLite**.

```mermaid
erDiagram
    USERS {
        uuid id PK
        string username
        string email
        string password_hash
        string role
        timestamp created_at
    }

    SUBJECTS {
        uuid id PK
        string name
        string description
        string icon
        timestamp created_at
    }

    TOPICS {
        uuid id PK
        uuid subject_id FK
        string title
        string description
        int order_index
        string difficulty_level
        timestamp created_at
    }

    DOCUMENTS {
        uuid id PK
        uuid topic_id FK
        uuid uploaded_by FK
        string file_name
        string file_path
        string file_type
        string vector_collection_id
        timestamp created_at
    }

    CHAT_SESSIONS {
        uuid id PK
        uuid user_id FK
        uuid topic_id FK
        string session_title
        timestamp started_at
        timestamp ended_at
    }

    MESSAGES {
        uuid id PK
        uuid session_id FK
        string role
        text content
        json metadata
        timestamp created_at
    }

    QUIZZES {
        uuid id PK
        uuid topic_id FK
        string title
        string difficulty
        int time_limit_mins
        timestamp created_at
    }

    QUESTIONS {
        uuid id PK
        uuid quiz_id FK
        text question_text
        string question_type
        json options
        string correct_answer
        text explanation
    }

    QUIZ_ATTEMPTS {
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

    USERS ||--o{ CHAT_SESSIONS : "starts"
    USERS ||--o{ QUIZ_ATTEMPTS : "completes"
    USERS ||--o{ USER_PROGRESS : "accumulates"
    USERS ||--o{ DOCUMENTS : "owns"
    SUBJECTS ||--o{ TOPICS : "houses"
    TOPICS ||--o{ CHAT_SESSIONS : "contextualizes"
    TOPICS ||--o{ QUIZZES : "generates"
    TOPICS ||--o{ DOCUMENTS : "indexes"
    TOPICS ||--o{ USER_PROGRESS : "evaluates"
    QUIZZES ||--o{ QUESTIONS : "contains"
    QUIZZES ||--o{ QUIZ_ATTEMPTS : "evaluated by"
    CHAT_SESSIONS ||--o{ MESSAGES : "logs"
```

---

## 🔌 5. Model Context Protocol (MCP) Integration

DeepTutor incorporates native **Model Context Protocol (FastMCP)** endpoints via `app/mcp_server.py` and `app/mcp_client.py`. This allows external IDEs and agents (e.g., Cursor, Claude Desktop, VS Code) to interact with DeepTutor's internal RAG pipeline and student data.

```mermaid
sequenceDiagram
    participant Client as External Client (Cursor / Claude / VS Code)
    participant MCP as FastMCP Server (DeepTutor)
    participant RAG as 4-Stage RAG Pipeline
    participant DB as DeepTutor DB / Vector Store

    Client->>MCP: Call mcp.tool("search_deeptutor_notes")
    MCP->>RAG: Generate query embedding & FAISS search
    RAG-->>MCP: Formatted source passages + page metadata
    MCP-->>Client: Markdown formatted response

    Client->>MCP: Call mcp.tool("get_student_memory")
    MCP->>DB: Query user mastery level, XP & weak areas
    DB-->>MCP: Student progress profile
    MCP-->>Client: Structured JSON / Markdown summary

    Client->>MCP: Call mcp.tool("generate_study_quiz")
    MCP->>RAG: Invoke quiz_generator with topic context
    RAG-->>MCP: Interactive Quiz JSON
    MCP-->>Client: Formatted Question & Options
```

### Exposed MCP Tools

1. **`search_deeptutor_notes(query: str, topic_id: str)`**
   - Performs semantic vector search on uploaded PDF textbook notes.
2. **`get_student_memory(user_id: str)`**
   - Fetches mastery levels, strength/weakness analytics, and XP statistics.
3. **`generate_study_quiz(topic_id: str, difficulty: str, num_questions: int)`**
   - Dynamically crafts targeted practice quizzes directly from document context.
4. **`get_knowledge_graph_nodes(topic_id: str)`**
   - Exposes extracted 3D Knowledge Graph entities and semantic connections.

---

## 🚀 6. Infrastructure & Deployment Environment

- **Development Servers**:
  - Frontend: Vite Dev Server running on port `5173`.
  - Backend: FastAPI Uvicorn ASGI running on port `8000`.
  - Local AI: Ollama Daemon listening on `http://localhost:11434`.
- **Deployment Platform Configurations**:
  - **Netlify**: `netlify.toml` single-page application routing configurations.
  - **Vercel**: `vercel.json` rewrites and routing rules.
  - **Docker**: `Dockerfile` for multi-stage Python containerization.
  - **Automation Scripts**: `start.bat`, `add_user.py`, `reset_db.py`, `export_docling_markdown.py`.
