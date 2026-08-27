# DeepTutor Product Strategy Docs

Working set of strategy and planning documents, drafted 27 Aug 2026 on branch
`docs/product-strategy`. These are the source of truth for sprint planning; the
shareable web versions (artifacts) mirror an earlier revision.

| Doc | What it answers |
|---|---|
| [architecture-report.md](architecture-report.md) | What the system is today — stack, pipeline, risks |
| [monetization.md](monetization.md) | Where the profit is — unit economics, streams, pricing |
| [differentiation.md](differentiation.md) | How we beat free ChatGPT/Claude — the moat filter |
| [mvp-plan.md](mvp-plan.md) | Go-to-market staging: Solo → Family → Classroom |
| [homework-loop-spec.md](homework-loop-spec.md) | Technical spec for the homework / parent sign-off loop |
| [release-plan.md](release-plan.md) | Market release timeline (India / Sweden / UAE), reconciled with the MVP stages |
| [infra-and-cicd.md](infra-and-cicd.md) | Repo cleanup, target infra (~$15–20/mo), GitHub Actions CI/CD design |
| [architecture-pattern.md](architecture-pattern.md) | ADR-001: router→service→repository + typed RAG pipeline stages |
| [code-review-findings.md](code-review-findings.md) | Deep review of data/API/RAG layers — P0 security holes, defects, ticket register |
| [sprint-plan.md](sprint-plan.md) | Sprints 1–3, AI-assisted sizing, ticket-level plan |

## Decision log

- **2026-08-27** — MVP staging agreed: individual signup first (free, time-boxed,
  proof only) → parent+child (billing launches here; the parent is the payer)
  → school/institute B2B (profit phase). Rationale in [mvp-plan.md](mvp-plan.md).
- **2026-08-27** — Differentiation thesis: never compete on chat; build features
  that are multi-person or stateful-over-time. Homework/parent sign-off loop is
  the flagship. Rationale in [differentiation.md](differentiation.md).
- **2026-08-27** — Market order: India (volume/proof) → Sweden (sovereign B2B
  margin) → UAE (ARPU), per [release-plan.md](release-plan.md).
- **2026-08-27** — Code review (3 parallel deep reviews) found 10 P0 security/
  tenancy holes on the live API; Sprint 1 opens with a hotfix train ahead of
  infra work. ADR-001 layered pattern adopted for Sprint 2 migration; sprint
  sizing assumes AI-assisted development (review bandwidth is the constraint).
- **2026-08-27** — Infra decision: stateless Docker backend on Render Starter +
  Netlify + Neon + Upstash + Pinecone/S3 free tiers (≈$15–20/mo); all deploys
  via GitHub Actions; TextBook PDFs purged from git history. Rationale in
  [infra-and-cicd.md](infra-and-cicd.md).
