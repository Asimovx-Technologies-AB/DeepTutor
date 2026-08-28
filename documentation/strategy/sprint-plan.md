# Sprint Plan — Sprints 1–3

*Drafted 27 Aug 2026. Two-week sprints. Supersedes the S1–S3 rows of the
skeleton in mvp-plan.md. Tickets reference code-review-findings.md (D#/A#/R#)
and infra-and-cicd.md.*

## How this plan is sized (AI-assisted team)

The team develops with Claude/Codex, so conventional person-day estimates are
wrong in both directions. Sizing model used here:

- **AI-cheap** (hours, not days): well-specified mechanical work — CRUD,
  test generation, module splits against a pinned behavior baseline, CI YAML,
  Dockerfiles, dedup refactors. These are batched aggressively.
- **Human-bound** (the real sprint constraints): PR review bandwidth,
  decisions, credentials/account setup, coordinated events (the history
  rewrite), and verification on real infrastructure. Sprints are
  throughput-limited by *review*, not by writing code.
- Working agreements: small single-purpose PRs; CI green is the reviewer's
  floor; every refactor ticket starts from AI-generated characterization
  tests; `CLAUDE.md`/`AGENTS.md` carries the pattern rules so the AI tools
  enforce ADR-001 by default; tickets are assigned to avoid two people (or
  two AI sessions) touching the same file in one sprint.

Each ticket lists **[AI]** what the tools produce and **[H]** the human part.

### One deviation from "infra first," with reasoning

Infra is the spine of Sprint 1 as agreed — but the backend is *already live on
the internet* with a hardcoded auth backdoor, an unauthenticated SSE endpoint,
and cross-tenant read/write/delete holes (P0-1…P0-10). Those can't wait two
weeks behind Docker. Sprint 1 therefore opens with a 2–3 day security hotfix
train that ships on the *current* infra, then the infra work proceeds.

---

## Sprint 1 — "Safe & Buildable"

**Goal:** the live API has no known P0 holes; the repo is clean, Dockerized,
and every PR runs CI. **Demo on sprint review:** a PR fails CI on a lint/test
error; the P0 exploit scripts all return 401/403/404.

| ID | Ticket | Source | Size |
|---|---|---|---|
| S1-1 | **P0 hotfix train** (days 1–3, sequenced PRs): remove demo-token; authenticate SSE; ownership checks on chat/quiz/session routes; user-scope all topic deletes; strip `correct_answer` from unsubmitted quiz GET; sanitize filenames (UUID keys); require `SECRET_KEY` from env; drop email from leaderboard; fix premium endpoint (or disable it — no payment flow exists yet: **decision needed**); fix quiz route shadowing. [AI] fixes + regression tests per hole. [H] review each PR, redeploy, re-run exploit checks. | D1, A1, A2, A7, P0-* | AI-cheap ×10, review-heavy |
| S1-2 | **Repo purge + history rewrite** (day 1, before branches pile up): TextBook→S3, untrack eval binaries/reports, delete scratch/dead files, dedupe .gitignore, `git filter-repo`, force-push. [AI] scripts + .gitignore. [H] coordinate: everyone merges/stashes, re-clones same day. | infra §cleanup | Human-coordination |
| S1-3 | **Characterization test suite**: httpx/TestClient tests pinning current JSON responses of every live endpoint against temp SQLite; fixtures for two users (tenancy assertions). This is the safety net for all Sprint-2/3 refactors. [AI] generates the bulk. [H] spot-check the pins are correct, not just green. | D3 | AI-cheap, large |
| S1-4 | **Dependency split + Docker**: requirements-core/-ocr split; multi-stage Dockerfile (one image: API + ARQ worker via CMD); docker-compose (postgres, redis, api, worker) for prod-shaped local dev. [AI] all of it. [H] verify image size (<1 GB) and compose-up on two machines. | infra §docker | AI-cheap |
| S1-5 | **ci.yml + branch protection**: ruff + pytest (S1-3 suite) + oxlint + tsc + vite build, path-filtered; protect `main` (PR + green CI, no force-push). [AI] workflow. [H] repo settings, secrets. | infra §cicd | AI-cheap |
| S1-6 | **Alembic baseline + fail-loud DB**: initial autogen migration; delete create_all + ALTER loop; SQLite fallback only behind explicit `ALLOW_SQLITE_FALLBACK` (off in deploys). | D2, P0-9 | AI-cheap |
| S1-7 | **Accounts & environments** (pure human, start day 1, has lead times): Render Starter upgrade, Upstash, Sentry, UptimeRobot, S3 seed bucket, GitHub Environments (staging/production) with secrets. | infra | Human-only |
| S1-8 | **CLAUDE.md / AGENTS.md**: five ADR-001 rules, layout map, run/test commands, never-do list — so every AI session from Sprint 2 onward codes to the pattern. [AI] draft from architecture-pattern.md. [H] team reads and agrees in planning. | ADR-001 | AI-cheap |

**Deferred-by-design:** no feature work, no pattern migration yet (tests first).

---

## Sprint 2 — "Stateless & Deployed"

**Goal:** merge→staging→approve→production with no manual steps; a Render
restart loses zero data; the layered pattern exists in the codebase.
**Demo:** kill the staging instance mid-index; job resumes from queue, graph
data intact in Postgres.

| ID | Ticket | Source | Size |
|---|---|---|---|
| S2-1 | **Graph KV → Postgres JSONB**: `PostgresTopicGraph` behind the existing `GraphKVStore` façade, delta upserts (not whole-graph push); migrate the half-built `_sync_to_cloud` path; remove FS assumptions (mkdir/rmtree). | R4, infra §stateless | AI-cheap against S1-3 tests |
| S2-2 | **Quick RAG correctness batch**: fix cache invalidation (two-level dict by topic); repoint graph-viz + quiz suggestions to `active_graph_store` (+`get_entities()`), delete `graph_store.py`; harden SSE (error event + guaranteed `done`). | R1, R2, R7 | AI-cheap, small |
| S2-3 | **ARQ worker + job status**: indexing through Redis queue; DB-backed job-status table replacing in-memory `_indexing_status`; frontend polls status endpoint. | A6(part), infra | AI-cheap + [H] verify on staging |
| S2-4 | **Deploy workflows**: build→GHCR→staging→smoke `/health`→gated production; Netlify deploy via Actions (auto-build off); delete vercel.json; remove bare-root mounts (frontend confirmed /api-only); delete `ServerWarmupNotice`. | A8, infra §cicd | AI-cheap + [H] approvals |
| S2-5 | **Pattern scaffold + database.py split**: create `services/ repositories/ schemas/`; move the ~55 functions into per-domain repositories with session-per-request (`get_db` owns the transaction); routes become sync `def` (threadpool) until async engine; Pydantic response schemas (password_hash excluded by construction). The characterization suite is the referee. | D4, D7, ADR-001 | AI-cheap but review-heavy — split across ≥6 PRs |
| S2-6 | **Tenancy schema fix**: `user_id` on Flashcard/Quiz (+FKs, indexes, backfill migration); re-scope remaining topic-filtered queries. | D6 | AI-cheap |
| S2-7 | **Quotas + metering**: per-user counters (uploads MB, pages, questions/day) enforced in the service layer; cost-per-user view (queries or dashboard). | mvp R0 | AI-cheap + [H] set limits |
| S2-8 | **Data-isolation test in CI**: two-user fixture proves cross-tenant retrieval/deletes impossible (API + vector namespaces). Runs in ci.yml forever. | mvp R0 | AI-cheap |

---

## Sprint 3 — "Refactor Done & Beta-Ready"

**Goal:** the three god-modules are gone; Solo MVP polish underway; beta
onboarding can start the following sprint. **Demo:** upload→first quiz on a
phone in under 2 minutes, on production, by someone outside the team.

| ID | Ticket | Source | Size |
|---|---|---|---|
| S3-1 | **Split graph_rag.py** per the reviewed module map (prompts/, intent_router as data table, query_utils, indexer, retriever, answerer; thin façade). Mechanical against S1-3 + eval gate. | R5 | AI-cheap, review-heavy |
| S3-2 | **Dismantle notes.py**: extract `LLMCompletionService` + JSON repair (shared with documents.py concept-explain and quiz_generator); prompts → prompt module; 620-line fallback block → data/templates; `NoteGenerationService`; fix the `is_curriculum_topic` NameError; route ≤ ~30 lines. | A4, A5, P1 | AI-cheap |
| S3-3 | **SectionCleanupService + dedupe batch**: one async cascade replacing the three copies; single collection-id helper; shared streak service (dashboard+progress agree); stats endpoint read-only. | A3, A8 | AI-cheap |
| S3-4 | **Async hygiene + memory bounds**: `to_thread` around file/CPU work in async routes; logging instead of print; no raw `str(e)` to clients; LRU eviction on per-topic FAISS/graph caches; storage Protocols with async methods. | A6, R3, R8 | AI-cheap |
| S3-5 | **Typed columns migration**: JSON-Text → JSONB, string timestamps → `DateTime(timezone=True)`; drop getter/setter shims; leaderboard/student-record N+1 rewrite with joins. | D5, D8 | AI-cheap, needs careful [H] migration review |
| S3-6 | **eval.yml**: RAGAS/DeepEval gate against staging, nightly + PR label; thresholds from current baseline (regression = red). | mvp | AI-cheap + [H] threshold decision |
| S3-7 | **Solo onboarding + mobile pass**: upload→first-quiz flow with progress states (uses S2-3 status), empty states, mobile-responsive chat/quiz/flashcards, in-app feedback (thumbs + wrong-answer report). | mvp MVP-1 | AI-cheap + [H] real-device QA |
| S3-8 | **Beta runbook + cohort prep** (human): Sentry alert routing, support inbox, beta invite list (Kerala HSS contacts), textbook-licensing check, privacy note for beta users. | mvp R1 | Human-only |
| S3-9 | **Frontend/backend route drift fix**: reconcile `documents list` / `streaks` / `attempts` (implement or remove callers). | A7(part) | AI-cheap, small |

**Retire at end of S3:** legacy `vector_store.py` (Chroma) — migrate the 5
secondary readers onto `pipeline`/`storage` during S3-2/S3-3 and delete it
with `document_processor.py` if S3 capacity allows; otherwise first item of
the Sprint-4 debt budget (R6).

---

## Standing rules

- Scope is cut to protect sprint goals; the P0 list and S2-8 isolation test
  are never the cut.
- Every PR: single purpose, characterization tests stay green, pattern rules
  from CLAUDE.md apply to touched code (boy-scout).
- Sprint review = the demo lines above, run live, not slides.
- After Sprint 3, planning returns to mvp-plan.md (Family build starts) with
  the rolling 20% debt budget (async engine, R6 completion).
