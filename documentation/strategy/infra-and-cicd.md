# Infrastructure, CI/CD & Repo Cleanup Plan

*Drafted 27 Aug 2026, from measured repo state. Feeds Sprint 1–2 of
mvp-plan.md. Prices are list prices as of drafting — verify before committing.*

## Where we are (measured)

| Fact | Evidence | Consequence |
|---|---|---|
| Git pack is **81 MB**, ~84 MB of it three PDFs in `TextBook/` | `git count-objects` | Slow clones/CI checkouts forever unless purged from history |
| Tracked junk: `backend/evaluations/chroma_data/*.bin`, eval result runs, root screenshot/PDF | `git ls-files` | Noise; some are generated artifacts |
| `.gitignore` is decent — runtime caches on disk are *untracked* | verified | Cleanup is smaller than it looked |
| **No `.github/` directory** | verified | CI/CD is greenfield — no legacy to fight |
| **Graph store (`lightrag_data/`) is local JSON on disk** | `config.py`, `storage/graph_kv.py` | On Render, disk is ephemeral → **GraphRAG data is lost on every deploy/restart**. This is a live correctness bug, not tech debt |
| Same for `vlm_cache/`, `image_search_cache/`, `faiss_data/` | config | Caches are rebuildable (cost, not correctness); FAISS unused when Pinecone is the backend |
| `requirements.txt` installs easyocr (→ torch), docling, chromadb, faiss | requirements.txt | ~4–6 GB env, slow builds, forces big instances — for features **disabled by default** (`ENABLE_DOCLING=False`) |
| Frontend deployed to Netlify **and** Vercel; backend on Render free tier (cold-start notice component exists) | configs, `ServerWarmupNotice.tsx` | Two frontend paths to keep consistent; free-tier backend can't run a beta |
| Sync SQLAlchemy in async FastAPI; no Alembic | database.py | Known; scheduled in foundation work |

## Target architecture principle: **a stateless backend**

The single investment that makes every hosting choice cheap and every scale
step trivial: no data the backend can't afford to lose may live on its disk.

| State | Today | Target |
|---|---|---|
| Uploads | S3 (already) | S3 — keep |
| Relational data | Neon Postgres (SQLite fallback) | Neon — keep; **remove the silent SQLite fallback in deployed envs** (fail loud; fallback is a local-dev flag) |
| Vectors | Pinecone (already) | Pinecone — keep; FAISS remains the local/sovereign backend only |
| **Graph KV (entities/relations/triplets)** | **local JSON files** | **Postgres JSONB tables** (a `graph_kv` table with section-scoped keys is a near drop-in for `storage/graph_kv.py`; no new service needed) |
| VLM / image-search caches | local disk | S3-backed (key = existing content hash) with local dir as a warm layer; losing the local layer costs money, not data |
| Job queue (new) | — | Redis (Upstash free tier) + ARQ worker |

Once this holds, the backend is a disposable container: Render today, VPS or
Azure tomorrow, horizontal scaling whenever needed — no migration events.

## Recommended infra (beta, 25–50 users → scales to launch)

**Recommendation: managed-everything, one paid host, Docker from day one.**

| Layer | Choice | Monthly cost | Minimum spec / why |
|---|---|---|---|
| Frontend | **Netlify free** (drop Vercel) | $0 | Static SPA; 100 GB bandwidth is ample. One host = one deploy path |
| Backend API | **Render Starter** (Dockerized) | $7 | 0.5 vCPU / 512 MB runs the slim image; bump to Standard ($25, 2 GB) only if parsing p95 says so. Paid tier kills cold starts — delete `ServerWarmupNotice` |
| Indexing worker | **Same image, ARQ worker on Render** | $7 | Separate process so a 500-page parse never blocks the API. (Frugal start: run worker in the API container under one supervisor and split when metering says so — saves $7 at the cost of isolation) |
| Queue | **Upstash Redis free** | $0 | 256 MB free tier is far beyond beta needs |
| Postgres | **Neon free** | $0 | 0.5 GB storage fine for beta; **branching gives free staging + per-PR CI databases** — the main reason to stay. Launch plan ($19) at public launch |
| Vectors | **Pinecone serverless starter (free)** | $0 | Fits beta scale; already integrated |
| Object storage | **AWS S3** (already) | ~$1–3 | Keep; revisit Cloudflare R2 (zero egress) at launch, not now |
| Errors/monitoring | **Sentry free + UptimeRobot free** | $0 | Backend + frontend DSNs; /health checks |
| CI/CD | **GitHub Actions** | $0 | 2,000 free min/mo (private repo) is enough with path filters and a slim image |
| **Total run cost** | | **≈ $15–20/mo** | Vs. ~$40–60 on Azure App Service for the same shape |

**Why not a single cheap VPS (Hetzner ~€8/mo, 4 vCPU/8 GB)?** Best raw
price/performance and we *will* want Docker Compose anyway for the Swedish
sovereign bundle (R3) — but it puts OS patching, backups, TLS, and firewall on
a fresher team during the exact weeks they must focus on product. Revisit at
R3 when the sovereign bundle forces us to master Compose anyway. Azure mapping
exists (Static Web Apps + App Service + Flexible Postgres) if credits or a
customer demand it; the Docker + stateless work makes that move config-only.

**The "initial investment" is engineering time, not hosting spend:**
~1 sprint (2 weeks) of the foundation sprint pays for Dockerfiles, the
graph-KV-to-Postgres move, requirements split, and the workflows below.
After that, run cost is a rounding error against the Gemini/Pinecone bill.

## Docker & build slimming (prerequisite for cheap infra)

1. **Split Python deps** — `requirements-core.txt` (fastapi, sqlalchemy,
   pymupdf, pdfplumber, pinecone, google-generativeai, openai, rank-bm25,
   networkx, httpx, arq…) vs `requirements-ocr.txt` (easyocr, docling,
   pytesseract). Core image ≈ &lt;1 GB and runs in 512 MB RAM; the OCR extra is
   only installed where `ENABLE_DOCLING=True` (not in beta).
2. `backend/Dockerfile` — multi-stage, non-root, uvicorn entrypoint;
   `CMD` overridable to `arq app.worker.WorkerSettings` so **one image serves
   both API and worker**.
3. `docker-compose.yml` at repo root — postgres + redis + api + worker for
   local dev (every fresher gets prod-shaped dev in one command) and the seed
   of the R3 sovereign bundle.
4. Push images to **GHCR** from CI; Render deploys by image reference.

## CI/CD: everything through GitHub Actions

```
.github/workflows/
  ci.yml               # every PR
  deploy-frontend.yml  # push to main, paths: frontend/**
  deploy-backend.yml   # push to main, paths: backend/**
  eval.yml             # nightly + manual: RAGAS answer-quality gate
```

- **ci.yml** — path-filtered jobs:
  - backend: ruff + pytest (unit + the data-isolation test) against a
    **per-PR Neon branch** (created/deleted by the workflow) + fakeredis;
  - frontend: oxlint + `tsc -b` + `vite build`.
- **deploy-backend.yml** — build → push GHCR → deploy to Render **staging**
  → smoke-test `/health` → deploy **production** behind a GitHub Environment
  approval. Secrets live in GitHub Environments (staging/production), never in
  the repo.
- **deploy-frontend.yml** — build with production env → `netlify deploy
  --prod` via CLI. **Turn off Netlify's own git auto-build** so Actions is the
  single deploy path (a frontend deploy can then be gated on backend health).
- **eval.yml** — runs the RAGAS/DeepEval suite against staging nightly and on
  a `run-eval` PR label; fails if scores regress past thresholds. Socratic-leak
  eval joins in MVP-2.
- Branch protection on `main`: PR required, CI green required, no force-push.

Deploy flow the team lives with: merge PR → CI → staging automatically →
one-click approve → production. No SSH, no dashboards, no manual steps.

## Repo cleanup (ordered, with blast radius)

1. **Purge `TextBook/` from git** (move PDFs to S3 seed bucket; document the
   path in README). Then **rewrite history** with `git filter-repo` to drop the
   81 MB pack to ~1–2 MB. ⚠️ Requires one coordinated force-push + fresh clones
   — do it now while the team is 3–4 people, never later. (Fallback if rewrite
   is vetoed: remove going forward and accept the heavy history.)
2. **Untrack generated artifacts**: `backend/evaluations/chroma_data/`,
   `eval_results_run*/`, `eval_report.*`, root `Screenshot*.png`,
   `DeepTutor_API_Documentation.pdf` (regenerable from /docs). Keep
   `eval_dataset.json` + eval scripts — they're source. Extend `.gitignore`
   accordingly (also dedupe its repeated blocks).
3. **Deduplicate docs**: root `README/PROJECT_OVERVIEW/techstack/
   implementation_plan` vs `documentation/` copies → single `documentation/`
   tree + slim root README; refresh to v2 reality (docs currently describe the
   v1 Ollama/Chroma stack).
4. **Delete dead weight**: `frontend/src/scratch/` (conflict-resolution
   scripts), `backend/app/api/animation.py` (0 bytes), `backend/test.txt`,
   stale root dumps; fold `api/endpoints/images.py` into `api/` proper.
5. **Dependency prune** (with the split): drop `pypdf2` (superseded by
   `pypdf`), `aiosqlite` (unused by the engine), decide `chromadb` (legacy
   fallback — remove; FAISS is the local backend) — each removal shrinks the
   image and the audit surface.
6. **Config hygiene**: remove the dual router mounting (`/api` + root) after
   the frontend confirms it only uses `/api/*`; delete `vercel.json` once
   Netlify is confirmed the sole frontend host.

## Refactors that are part of infra (not the 20% debt budget)

- **Graph KV → Postgres JSONB** — fixes the data-loss bug; ~2–3 days against
  the existing `storage/` interface.
- **Fail-loud DB config in deployed envs** — the silent SQLite fallback can
  hide a Postgres outage and quietly fork user data on an ephemeral disk.
- **Indexing → ARQ worker + job-status endpoint** — already in MVP-1 scope;
  lands together with the queue.

Deferred to the rolling 20% debt budget (unchanged): async DB access, splitting
`graph_rag.py` (~85 KB) and `api/notes.py` (~60 KB).

## Sprint 1–2 placement

Everything above fits the existing S1–S2 "Foundation" slots in mvp-plan.md:

- **S1**: repo purge + history rewrite (day 1–2), requirements split,
  Dockerfile + compose, `ci.yml`, secrets/CORS/rate-limit hardening.
- **S2**: graph-KV→Postgres, ARQ worker + Upstash, deploy workflows +
  staging/production environments, Sentry/UptimeRobot, Alembic baseline,
  quotas + metering.

Exit proof for the infra slice: a PR merged to `main` reaches staging with no
human steps; a deliberate Render instance restart loses **zero** user data.
