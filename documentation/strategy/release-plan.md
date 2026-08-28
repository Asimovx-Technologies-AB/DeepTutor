# Release Plan (v2)

*Drafted 27 Aug 2026; revised same day to fold in the MVP staging (mvp-plan.md).
Key change from v1: billing moved from the India public launch to the Family
stage — the parent is the payer; the homework loop became the Sweden pilot
centerpiece.*

## Strategy in one paragraph

The hook is identical everywhere — *your own textbook becomes your tutor*:
answers, quizzes, flashcards, and study plans generated strictly from the
student's uploaded material, with citations and a hallucination guard. What
changes per market is packaging: **India** buys exam outcomes at a low price
(our VLM scanned-PDF parsing is a quiet moat there); **Sweden** buys privacy
and accountability — the fully-local mode becomes "no student data leaves your
building," and the läxa/parent sign-off loop is what a school actually pays
for; **UAE** buys premium bilingual tutoring, entered via CBSE expat schools
where India content works day one.

## Timeline

| Release | MVP stage | When | Market focus |
|---|---|---|---|
| R0 Foundation | MVP-1 (part) | Sep–Oct 2026 | internal |
| R1 Private beta | MVP-1 | Nov 2026 – Jan 2027 | India (Kerala HSS, free) |
| R2 Family launch | MVP-2 | Feb–Apr 2027 | India public + Swedish family soft-launch |
| R3 Classroom & Sweden pilot | MVP-3 | Mar–Jun 2027 (parallel track) | India institutes + 1–2 Swedish schools |
| R4 UAE entry | post-MVP-3 | Jul–Oct 2027 | UAE (Sept school year) |

R3 overlaps R2 deliberately: Swedish procurement is slow, so conversations
start early while engineering focus stays on India. If R2 slips, R3
engineering slips with it — never the reverse.

## R0 — Foundation (Sep–Oct 2026, internal only)

Hardening and process; no features. Senior engineer engaged for security &
data-layer review.

- Secrets to env/Key Vault; kill default `SECRET_KEY`; restrict CORS
- Rate limiting, email verification, password reset
- Per-user quotas (upload MB, pages/mo, questions/day) + usage metering
- Data-isolation test in CI (user A can never retrieve user B's chunks)
- Background indexing → job queue with visible progress
- Alembic; CI on every PR; staging env; repo hygiene; docs refreshed to v2

**Gate:** review passed; isolation test green; runaway users capped; cost/user
dashboard live.

## R1 — Private beta (Nov 2026 – Jan 2027, 25–50 invited students)

Free Kerala HSS cohort on preloaded textbooks + own notes. Onboarding
(upload → first quiz < 2 min), mobile pass, in-app feedback, RAGAS eval as CI
gate, weekly cost review, textbook licensing verified.

**Gate:** ≥10 weekly-active by week 6; W4 retention ≥ 40%; answer-flag < 5%;
unit cost < 30% of intended family price. **If unmet, iterate here — do not
launch.**

## R2 — Family launch (Feb–Apr 2027, timed to board-exam season)

First revenue. Parent+child linking, weekly parent digest, homework-lite with
one-tap sign-off, Socratic homework mode (per homework-loop-spec.md).
Billing: parent pays — ₹299 exam pass (hero SKU), ₹149/mo, ₹999/yr; UPI +
Stripe. Privacy policy, ToS, deletion/export (GDPR-grade once, reused for
Sweden). Hindi as fourth language. Quiet Swedish-family soft launch (UI ready).

**Gate:** 100 paying families in 8 weeks; margin/user > 60%; digest open rate
> 40%; support load sustainable.

## R3 — Classroom & Sweden pilot (Mar–Jun 2027, parallel B2B track)

- **India institutes (fast clock):** teacher/class entities, class dashboard,
  per-seat bundles, institute-branded parent reports; founder-led sales.
- **Sweden schools (slow clock):** sovereign bundle (dockerized Ollama + FAISS
  + SQLite + local graph), install guide, GDPR pack/DPAs, Swedish
  answer-quality eval, thin read-only teacher view; 1–2 pilot schools.
  BankID sign-off only if a pilot demands it.

**Gate:** ≥2 paying institutes OR 1 signed school pilot (paid/LOI); sovereign
install reproducible < 1 day; renewal intent in writing.

## R4 — UAE entry (Jul–Oct 2027, aligned to September school year)

English-first soft launch via CBSE/British expat schools; finish Arabic
properly: full RTL audit, Arabic parsing/retrieval eval in CI, premium AED
pricing (geo-fenced), tutoring-center white-label, curriculum packs (CBSE →
IGCSE/IB), native-speaker localization QA.

**Gate:** Arabic eval within 10% of English before any Arabic marketing;
2 tutoring centers or 200 B2C users by end of Q4 '27.

## Cross-release workstreams

- **Quality bar:** RAGAS/DeepEval in CI from R1; each market adds its language
  to the eval set before launching there; Socratic-leak eval joins in R2.
- **Unit economics:** pricing decisions always follow measured cost.
- **Compliance:** deletion/export built once (R2), reused R3/R4; DPA register
  for Google, Pinecone, hosts.
- **Tech debt:** ~20% of each sprint (async DB, split `graph_rag.py`/`notes.py`).
- **Moat filter:** every feature passes differentiation.md's test.

## Top risks

1. **AI cost blowout** — quotas/metering in R0 are non-negotiable.
2. **Retention, not acquisition** — R1's hard gate before launch spend.
3. **Big-player squeeze** — stay where free chat can't follow: syllabus
   grounding, scanned PDFs, homework loop, sovereign deployments.
4. **Team seniority** — senior review R0, external pen-test before R2, thin
   scopes.
5. **Three markets, one team** — market tracks are sales-led with thin
   engineering slices; product track has priority.

## Operating cadence

Two-week sprints; releases are trains (cut scope, not dates); one-week freeze +
regression before each public release; monthly KPI review against this plan —
gates may not be weakened retroactively.
