# Architecture Report

*Compiled 27 Aug 2026 from the repository (v2.0.0, branch `main`). Where older
docs disagree with the code, the code was treated as authoritative.*

## Summary

DeepTutor is a two-tier monorepo: `frontend/` (React 19 + Vite + TypeScript +
Tailwind v4, deployed to Netlify/Vercel) and `backend/` (FastAPI + SQLAlchemy,
deployed to Render). Students upload PDFs; the backend parses, chunks, embeds,
and indexes them into a vector store and a lightweight knowledge graph, then
serves grounded chat, quizzes, flashcards, study plans, and notes from that
index.

Nearly every infrastructure concern is **provider-switchable via config**
(`backend/app/core/config.py`):

| Concern | Default | Alternatives |
|---|---|---|
| LLM | Gemini (`gemini-3.5-flash-lite`) | Ollama (`llama3.1`) |
| Embeddings | Gemini | OpenAI, Ollama `nomic-embed-text` |
| Vector store | Pinecone Serverless | FAISS HNSW, ChromaDB (legacy) |
| Graph store | LightRAG-style JSON KV | NetworkX (legacy) |
| Database | Neon PostgreSQL | automatic silent fallback to SQLite |
| Documents | AWS S3 (eu-north-1) | local disk |

The fully-local combination (Ollama + FAISS + SQLite + local graph) still works
and is the basis of the Swedish "sovereign deployment" pitch.

## The four-stage RAG pipeline (`backend/app/rag/`)

1. **Parse & chunk** — PyMuPDF primary; pdfplumber/pypdf fallbacks; optional IBM
   Docling with OCR. Gemini 2.5 Flash acts as a VLM for scanned/image-heavy
   pages (disk-cached, capped at 50 pages/doc). Semantic chunking, 350–650
   words/chunk.
2. **Embed & extract** — multi-provider embedder; entity extractor builds
   entities/relations/confidence-scored triplets per section.
3. **Store** — vectors to Pinecone (indexes `textbook` + `deeptutor`) or FAISS;
   graph triplets to JSON-KV; originals to S3.
4. **Retrieve & generate** — hybrid dense + BM25 fused with RRF (0.7/0.3), BM25
   reranking, 2-hop graph traversal, TTL caches, hallucination guard. HyDE and
   query expansion exist but are disabled for latency.

Retrieved context feeds the generators: chat, quizzes, flashcards, study plans,
smart notes.

## Backend

FastAPI with 12 routers (auth, chat, documents, quiz, flashcards, progress,
study plan, leaderboard, notes, dashboard, images, MCP), each mounted at both
`/api/…` and root. JWT auth (HS256, 7-day expiry) with bcrypt. 14 SQLAlchemy
models. Engine targets Neon Postgres and silently falls back to local SQLite;
schema is `create_all` plus hand-rolled `ALTER TABLE` lists — no migration
tool. FastMCP server + in-process client. Serper-powered verified image search.
RAGAS/DeepEval evaluation harness with saved runs in `backend/evaluations/`.

## Frontend

React 19, Vite 8, TS 6, Tailwind 4. ~18 pages. Zustand stores (auth, chat,
subject, language) + TanStack React Query over Axios (`VITE_API_BASE_URL`,
default Render URL). react-markdown with GFM/KaTeX/highlight.js/Mermaid.
UI languages already implemented: **English, Swedish, Arabic** (
`src/stores/languageStore.ts`, `src/utils/translations.ts`).

## Deployment topology

| Component | Where |
|---|---|
| Frontend | Netlify and Vercel (both configs present) |
| Backend | Render (`deeptutor-api-udv2.onrender.com`) |
| Relational DB | Neon PostgreSQL (SQLite fallback) |
| Vectors | Pinecone Serverless (us-east-1) |
| Documents | AWS S3 (eu-north-1) |
| AI providers | Google Gemini, Ollama, Serper |

## Known risks / debt

1. **Docs lag the code** — README/PROJECT_OVERVIEW describe the v1 local-only
   stack; code is v2 cloud-first.
2. **Security** — default `SECRET_KEY` in config; CORS open to `*`.
3. **Sync ORM inside async FastAPI** — blocking risk under load; aiosqlite
   installed but unused.
4. **No migration tool** — Alembic needed.
5. **Runtime artifacts committed** — VLM/image caches, lightrag data, eval
   outputs, `frontend/src/scratch/`.
6. **Monolith modules** — `rag/graph_rag.py` (~85 KB), `api/notes.py` (~60 KB).
