# Code Review Findings

*Three parallel deep reviews (data layer, API layer, RAG engine) run 27 Aug
2026 against `main`. Line numbers are as of that commit. Tickets referenced
as D# (data), A# (API), R# (RAG) from the per-layer lists at the bottom.*

## P0 — live security/tenancy holes (the backend is publicly deployed on Render)

| # | Defect | Where |
|---|---|---|
| P0-1 | Hardcoded `demo-token` backdoor grants an authenticated identity to anyone | `api/auth.py:107–116` |
| P0-2 | Chat SSE stream has **no auth**: `token` param accepted, never validated; anyone with a session_id can inject messages / burn LLM quota | `api/chat.py:205–235` |
| P0-3 | Cross-tenant reads/writes: get/delete another user's chat session; read/submit another user's quiz | `chat.py:77–98`, `quiz.py:163–251`, `database.py:226,584` |
| P0-4 | Topic-scoped (not user-scoped) deletes wipe **other users'** flashcards/quizzes/KGs | `documents.py:112,510`, `database.py:460–495,722–724` |
| P0-5 | Quiz GET returns `correct_answer` before submission | `quiz.py:196–204` |
| P0-6 | Path traversal: raw `file.filename` in disk paths and S3 keys | `documents.py:93,107`, `notes.py:172,224` |
| P0-7 | Default `SECRET_KEY` + 7-day tokens → forgeable auth if env unset | `core/config.py:23,25` |
| P0-8 | Leaderboard returns every user's email | `database.py:901` |
| P0-9 | Silent SQLite fallback: a Neon blip at boot forks all writes into an ephemeral local file | `database.py:32–34` |
| P0-10 | Premium upgrade endpoint calls a function that doesn't exist (`update_user_premium_status`) → 500; also no payment/authz check | `auth.py:85` vs `database.py:162` |

## P1 — broken features & correctness

- `GET /quiz/my-attempts` unreachable — route declared after `/{quiz_id}` and
  shadowed; the frontend calls it (`quiz.py:254`, `api.ts:221`).
- `notes.py:188` — `is_curriculum_topic` used before its (conditional) import
  → NameError on the custom-upload path; that flow can never work as written.
- Query-cache invalidation is a **no-op**: keys are SHA256 hashes, the
  invalidator substring-matches `topic_id` — stale answers survive re-index
  for the full TTL (`rag/cache.py:98–127`, `graph_rag.py:967`).
- Graph visualization endpoint reads the dead NetworkX store (never written)
  → always falls back; quiz suggestions call a nonexistent
  `get_entities()` swallowed by bare `except` (`documents.py:273–281`,
  `quiz.py:64,76`).
- Register has a check-then-insert race → 500 on concurrent duplicate email;
  `username` has no uniqueness at all (`auth.py:39–45`, `models.py:13`).
- In-memory indexing status dict + unbounded module caches — lost on restart,
  wrong under >1 worker (`documents.py:27,156`).
- SSE generator dies without a `done`/error event if the LLM call throws
  mid-stream — client hangs (`graph_rag.py:1415,1453`).
- Read-modify-write of JSON blobs without locking → lost updates
  (`database.py:787–851`); `GET /dashboard/stats` writes on read
  (`dashboard.py:139–144`).

## P2 — structural (feeds the pattern refactor)

- `core/database.py`: 1,378-line god-module — ~55 CRUD+business functions,
  hand-rolled dict serializers (leak `password_hash` by default), every helper
  its own transaction (no atomicity across calls), N+1s in leaderboard and
  student-record queries, sync engine blocking the event loop everywhere.
- `api/notes.py`: one 955-line route — ~180 lines of prompts, a 620-line
  hardcoded fallback-content block, LLM chain duplicated with documents.py.
- `rag/graph_rag.py` (1,497 lines): five responsibilities — two giant system
  prompts, a 520-line keyword intent-router, regex utils, indexer, and a
  300-line `query_stream` method. Split map exists (see R5).
- Two parse stacks: legacy `document_processor.py` (Docling) still live for
  notes/flashcards/study-plan; `pipeline/parser.py` for the main flow.
  Legacy `vector_store.py` (Chroma) still read by 5 secondary modules;
  `graph_store.py` (NetworkX) is dead once the viz endpoint is repointed.
- Triplicated cleanup cascade (documents.py ×2, chat.py), duplicated
  collection-id logic with divergent behavior, duplicated streak logic with
  divergent rules (dashboard vs progress).
- Whole-graph-in-memory + whole-graph-push-per-write in graph_kv (write
  amplification; unbounded per-topic RAM caches in FAISS/graph stores).
- Frontend/backend route drift: `documents list`, `progress streaks`,
  `quiz attempts` called by api.ts with no matching backend route.
- All timestamps stored as strings; JSON-as-Text columns with silent-corruption
  getters.

## Consolidated ticket register

**Data layer:** D1 auth hardening hotfix · D2 Alembic baseline + fail-loud DB
· D3 characterization tests · D4 split database.py → repositories +
session-per-request · D5 typed columns (JSONB/DateTime) migration · D6 tenancy
schema fix (user_id on Flashcard/Quiz) · D7 Pydantic response schemas ·
D8 aggregate query rewrite (leaderboard/student record).

**API layer:** A1 ownership enforcement pass (incl. SSE auth) · A2 filename
sanitization + shared upload service · A3 SectionCleanupService (dedupe ×3) ·
A4 LLMCompletionService + JSON repair (dedupe) · A5 dismantle notes.py route ·
A6 async hygiene (to_thread, logging, no str(e) to clients, DB-backed job
status) · A7 quiz route shadowing + answer leakage + route drift · A8 remove
bare-root mounts + dedupe streaks/CHAPTER_TITLES.

**RAG engine:** R1 fix cache invalidation · R2 repoint viz/quiz to
active_graph_store, delete graph_store.py · R3 async-safe storage Protocols ·
R4 Postgres JSONB TopicGraph (delta upserts) · R5 split graph_rag.py ·
R6 formalize 4-stage pipeline, retire document_processor.py · R7 harden SSE
stream · R8 bound memory (LRU eviction).

Sprint placement in [sprint-plan.md](sprint-plan.md).
