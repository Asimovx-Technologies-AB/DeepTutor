# Monetization Analysis

*Drafted 27 Aug 2026. All prices and costs are planning estimates, to be
replaced by measured data from metering (MVP-1). Conversions rounded: ₹87/$,
10.5 SEK/$, AED 3.67/$.*

## Verdict

Variable cost per active student is low — estimated **$0.20–0.50/month** on the
cloud stack once quotas hold — so 80%+ gross margins are achievable even at
Indian prices. But individual-student B2C is a **volume and proof engine, not a
profit engine**: students have the weakest willingness-to-pay in edtech. The
payer is the parent (B2C) or the institution (B2B). Profit pools, in order:

1. **B2B seats** — one institute/school sale covers hundreds of students.
2. **Swedish sovereign school licenses** — ~90%+ margin (school hardware runs
   the local Ollama/FAISS stack; near-zero AI provider cost to us).
3. **Gulf ARPU** — 15–20× India for the same product.
4. **Parent-paid family plans** — the real B2C model (see mvp-plan.md).

## Unit economics (cloud stack, quota-held)

Assumptions: ~60 questions/mo, 2 doc uploads/mo, VLM capped at 50 pages/doc,
caching on.

| Component | Est. / active user / month |
|---|---|
| LLM chat (Gemini flash-lite) | $0.03–0.08 |
| Embeddings (one-time/doc, cached) | $0.01–0.05 |
| VLM parsing (one-time/doc, cached — the volatile one) | $0.05–0.25 |
| Pinecone serverless | $0.05–0.15 |
| S3 / DB / compute share | $0.03–0.10 |
| **Total variable** | **≈ $0.20–0.50** |

At ₹149/mo (~$1.70) → **~82% gross margin**. The two things that break it are
uncapped VLM usage and heavy chat users — both quota problems, not pricing
problems. Quotas and per-user metering ship before any public user does.

## Revenue streams, ranked

| # | Stream | Price (est.) | Margin | Volume | Effort | Stage |
|---|---|---|---|---|---|---|
| 1 | India family/B2C subscription | ₹149/mo · ₹999/yr · **₹299 exam pass (hero SKU)** | 80–85% | Very high | Low | MVP-2 |
| 2 | India coaching-institute seats | ₹2–4 lakh/yr | ~80% | High | Medium | MVP-3 |
| 3 | Sweden sovereign school license | 60–150k SEK/yr + setup | ~90%+ | Low, sticky | High | MVP-3 |
| 4 | UAE premium B2C | AED 49–99/mo (geo-fenced) | ~80% | Medium | Medium | Post-MVP-3 |
| 5 | UAE tutoring-center white-label | AED 15–30k/yr | ~80% | Medium | Medium | Post-MVP-3 |

Deliberately later: curriculum-pack marketplace, mock-test partnerships, API
licensing of the scanned-PDF pipeline.

## Deal math (annual gross contribution, India-subscriber equivalents)

- 1 Swedish sovereign school ≈ **850** India subscribers
- 1 UAE tutoring center ≈ **430**
- 1 Indian coaching institute ≈ **230** (and the institute does the distribution)

A small team can close 5–10 B2B deals/year founder-led; acquiring 5,000 paying
consumers needs a marketing machine we don't have. B2C proves the product and
feeds the funnel; B2B pays for the company.

## Pricing principles

- **India**: price for the exam, not the month — the ₹299 3-month exam pass is
  the hero SKU; free tier capped hard (1 document, 10 questions/day, tuned from
  measured costs). Institutes resell per-seat bundles as their retention
  feature.
- **Sweden**: price the deployment, not the student. Anchor against tutoring
  staff cost and GDPR risk. The cheaper EU-cloud tier exists mostly to justify
  the sovereign license.
- **UAE**: premium is the positioning; never discount to Indian prices —
  geo-fence plans.

## CAC discipline

- India B2C CAC **< ₹200** (≈2-month payback): campus ambassadors, Kerala HSS
  teacher communities, referrals, exam-season SEO. No paid ads until organic
  retention is proven.
- B2B CAC is founder time, not money. Sweden and UAE start as network-driven
  founder sales.

## Product-owner scorecard

| Metric | Target |
|---|---|
| Gross margin / active user | > 75% |
| CAC payback (B2C) | < 2 months |
| Week-4 retention | > 40% |
| Exam-pass → annual conversion | > 15% |
| B2B seat renewal | > 80% |
| Answer-flag rate | < 5% |

## Profit risks

1. **Free-good-enough** (ChatGPT study modes) — defend with syllabus grounding,
   scanned-PDF handling, the homework loop, and deployments they structurally
   won't do. See differentiation.md.
2. **Quota rebellion** — if >10% of paying users hit caps, raise tiers, never
   silently raise caps.
3. **Seasonality cliff** — Indian revenue craters every April; exam-pass SKU and
   annual prepay smooth it; model cash accordingly.
4. **B2B stall** — if procurement runs 2× long (it often does), B2C must cover
   infra; keep fixed costs near zero until revenue data exists.
