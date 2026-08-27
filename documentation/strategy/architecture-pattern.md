# Architectural Pattern (ADR-001)

*Drafted 27 Aug 2026. Status: proposed → adopt in Sprint 2.*

## Decision

Adopt a **layered router → service → repository pattern** for the backend, and
formalize the RAG code as a **4-stage pipeline with typed stage interfaces**.
Encode both in `CLAUDE.md` / `AGENTS.md` at the repo root so every AI coding
tool (Claude, Codex) follows the pattern without being told each session.

Why this pattern: it is the most widely represented convention in AI training
data — assistants generate it correctly by default — it gives freshers an
unambiguous answer to "where does this code go?", and it makes the two current
god-modules (`api/notes.py`, `core/database.py`) mechanically splittable.

## Backend layout (target)

```
backend/app/
  api/            # routers: HTTP only — parse request, call ONE service, shape response
  services/       # business logic: orchestration, permissions, LLM prompt assembly
  repositories/   # ALL SQLAlchemy access; one repo per aggregate (users, quizzes, notes…)
  schemas/        # Pydantic request/response models (routers never expose ORM objects)
  core/           # config, db engine/session, security — no business logic
  rag/
    pipeline/     # stage implementations: parser, chunker, embedder
    storage/      # backends behind interfaces: vector, graph-kv, object
    generators/   # quiz, flashcards, study-plan, notes generation
  workers/        # ARQ task definitions (indexing, digests)
```

## The five rules (these go in CLAUDE.md / AGENTS.md verbatim)

1. **Routers are thin.** A route handler validates input (Pydantic schema),
   calls exactly one service function, returns a schema. No SQL, no prompts,
   no business rules in `api/`.
2. **Only repositories touch the database.** Services receive/return domain
   data; no `db.query(...)` outside `repositories/`.
3. **Every ownership check lives in the service layer** and is written as
   `service.assert_owner(user, resource)` — never inline in a router, never
   skipped.
4. **RAG stages communicate through typed dataclasses/Pydantic models**
   (ParsedDoc → Chunk[] → EmbeddedChunk[] → RetrievalResult). A stage may be
   swapped (config) without touching its neighbors.
5. **New code follows the pattern; touched code gets migrated.** No big-bang
   rewrite: when a ticket touches a legacy function, the ticket includes moving
   it to its proper layer (boy-scout rule, enforced in PR review).

## Working agreements for AI-assisted development

- `CLAUDE.md` / `AGENTS.md` at repo root carries: the five rules, the layout
  map, run/test commands, and "never do" items (no new deps without a ticket,
  no schema change without an Alembic migration, no secrets in code).
- **Characterization tests before refactors**: AI tools refactor large modules
  cheaply, but only safely against a pinned behavior baseline. Every split
  ticket starts with "generate characterization tests for current behavior."
- **Humans review, AI writes.** PR review is the throttle, so keep PRs small
  and single-purpose; CI (lint, tests, isolation test, eval gate) is the
  reviewer's floor, not their job.
- Migration order for the pattern: schemas → repositories → services extracted
  from the worst router down (`notes.py` first), routers thinned last.
