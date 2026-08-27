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

## Decision log

- **2026-08-27** — MVP staging agreed: individual signup first (free, time-boxed,
  proof only) → parent+child (billing launches here; the parent is the payer)
  → school/institute B2B (profit phase). Rationale in [mvp-plan.md](mvp-plan.md).
- **2026-08-27** — Differentiation thesis: never compete on chat; build features
  that are multi-person or stateful-over-time. Homework/parent sign-off loop is
  the flagship. Rationale in [differentiation.md](differentiation.md).
- **2026-08-27** — Market order: India (volume/proof) → Sweden (sovereign B2B
  margin) → UAE (ARPU), per [release-plan.md](release-plan.md).
