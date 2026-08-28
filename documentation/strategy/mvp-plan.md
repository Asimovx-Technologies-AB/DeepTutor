# MVP Plan: Solo → Family → Classroom

*Drafted 27 Aug 2026. This is the go-to-market staging; release-plan.md maps it
onto markets and dates.*

## The analysis behind the sequence

Proposed staging was: individual signup → parent+child → school. Assessment:

**As a build order it is correct.** Each stage is infrastructure for the next:
the homework loop can't be tested without parent+child accounts, and a school
can't be sold without a working, referenced parent loop. The alternative —
school-first, which some edtechs run — was considered and rejected: 6–12 month
procurement cycles, no reference customers, no cash flow to survive the wait,
and an early-career team shouldn't learn product basics inside an enterprise
pilot.

**As a revenue order it needed one correction: individual signup is not a
monetization phase.** Students have the weakest willingness-to-pay in edtech;
the payer is the parent (B2C) or the institution (B2B). Launching billing at
the individual stage would produce a false negative ("the product can't
monetize") because it asks the wrong person for money. Therefore:

- MVP-1 is **free, invite-only, and hard time-boxed** — a deliberate, capped
  cost center whose output is proof, not revenue.
- Billing launches at MVP-2 with the **parent as the payer**.
- MVP-3 is the profit phase (institutes, then schools).

## MVP-1 — "Solo" (~8–10 weeks)

**Goal:** prove students come back voluntarily. Nothing else.

**Scope**
- Individual signup; upload → chat/quiz/flashcards/study-plan loop polished
- Foundation work (non-negotiable, from release-plan R0): secrets/CORS/rate
  limiting, per-user quotas + metering, data-isolation test in CI, background
  indexing with visible progress, Alembic, staging env
- Mobile-responsive pass; onboarding: upload → first quiz < 2 minutes
- In-app feedback (thumbs + one-tap wrong-answer report)
- Invite-only cohort: 25–50 Kerala HSS students (textbooks already loaded)

**Explicitly out:** billing, parent/teacher anything, new languages, leaderboard
expansion.

**Exit gate (must pass to proceed):**
- ≥ 10 weekly-active students by week 6; W4 retention ≥ 40%
- Measured unit cost < 30% of intended family-plan price
- Answer-flag rate < 5%
- If not met: iterate here. Do not build MVP-2 on an unproven core.

## MVP-2 — "Family" (~8 weeks, build overlaps MVP-1 beta)

**Goal:** first revenue + first defensible differentiation, in one release.

**Scope**
- Parent role, parent↔child account linking (see homework-loop-spec.md)
- Weekly parent digest (plain language: time, scores, weak areas)
- Homework loop *lite*: parent- or plan-assigned tasks, due dates, verified
  completion (time-on-task + score), one-tap parent sign-off
- Socratic homework mode: tutor hints but never reveals answers on assigned work
- **Billing**: parent pays — ₹299 exam pass (hero SKU), ₹149/mo, ₹999/yr family
  plan; UPI + card; free tier capped from measured MVP-1 costs
- Public launch India timed to exam season; English + Swedish UI already exist —
  quiet soft-launch for Swedish families as a learning channel

**Exit gate:**
- 100 paying families within 8 weeks of billing launch
- Gross margin/user > 60%; parent-digest open rate > 40% (proves the loop is
  valued, not just tolerated)

## MVP-3 — "Classroom" (~10–12 weeks)

**Goal:** first B2B profit. Two motions on different clocks.

**Scope**
- Teacher role, Class + membership entities, teacher-assigned homework
- Class dashboard: completion, stuck students, class-wide weak areas
- **India motion (fast clock):** coaching-institute packaging — per-seat
  bundles, institute-branded parent reports; founder-led sales; institutes
  close in weeks
- **Sweden motion (slow clock, conversations start during MVP-2):** sovereign
  deployment bundle (dockerized Ollama + FAISS + SQLite + local graph),
  GDPR pack/DPAs, Swedish answer-quality eval; target 1–2 pilot schools
- BankID sign-off: scoped, only if a pilot school requires it

**Exit gate:**
- ≥ 2 paying institutes OR 1 signed school pilot (paid or formal LOI)
- Seat-deal gross margin ≥ 80%; pilot renewal intent in writing

## Sprint skeleton (2-week sprints — detail in sprint planning)

| Sprint | Focus |
|---|---|
| S1–S2 | Foundation: security, quotas, metering, CI, Alembic, job queue |
| S3–S4 | Solo polish: onboarding, mobile, feedback loop; beta cohort onboarded |
| S5 | Beta iteration from cohort data (retention gate checkpoint) |
| S6–S7 | Family: roles, linking, digest, homework-lite, Socratic mode |
| S8 | Billing + launch hardening; India public launch |
| S9–S11 | Classroom: teacher/class entities, dashboards, institute packaging |
| S12+ | Sovereign bundle + Sweden pilot support |

Standing rules: scope is cut to protect dates, never the reverse; ~20% of each
sprint reserved for tech debt (first targets: async DB access, splitting
`graph_rag.py` and `notes.py`); every feature must pass the moat filter in
differentiation.md.
