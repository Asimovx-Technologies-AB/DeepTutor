# 05 — Delivery Roadmap and Gates

## Strategy

Execute in evidence-gated stages. Work stops at each gate until the required customer or product evidence exists.

## Stage 0 — Scope and discovery

### Tasks

- Confirm Biology as the pilot vehicle, not long-term positioning.
- Select the initial Lgr22 concept subset.
- Recruit a qualified Swedish Biology teacher.
- Prepare the competitor benchmark material.
- Benchmark Alice, general AI products, and available Swedish learning platforms.
- Conduct 30 parent interviews.
- Create landing page and pilot application.
- Define consent, privacy, safety, and outcome-measurement approach.

### Gate 0

Proceed only when:

- at least 10 of 30 parents describe a meaningful preparation/visibility problem without being led;
- at least 5 are willing to join a time-bound pilot;
- existing products do not fully satisfy the workflow for those families;
- teacher review confirms that the proposed diagnostic and reporting approach is educationally credible.

## Stage 1 — Reliability foundation

### P0 tasks

- Persist processing jobs and stage progress.
- Restore processing status and subject state after refresh.
- Prevent blank or invalid subject routes.
- Implement idempotent retry and cancellation.
- Add failure investigation and administration.
- Establish parent/child ownership boundaries.
- Add model, prompt, curriculum, and cost version tracking.
- Add upload safety, quotas, and deletion.

### Gate 1

- No loss of processing state during refresh or browser closure.
- At least 95% of valid pilot files process without manual database intervention.
- Failed jobs provide an actionable reason and safe retry.
- Cross-account access tests pass.
- Cost per processed workspace is observable.

## Stage 2 — Curriculum and assessment foundation

### P0 tasks

- Model 25–40 Lgr22 Biology concepts.
- Define prerequisites and misconception library.
- Produce 150–200 reviewed assessment items.
- Implement diagnostic selection and scoring.
- Implement mastery evidence and confidence.
- Reserve reviewed unseen final items.
- Add teacher review workflow or controlled content administration.

### Gate 2

- Teacher approves supported curriculum coverage.
- Every assessment item has a reviewed answer and rubric.
- Diagnostic produces explainable concept evidence.
- The same input produces stable, bounded scoring.
- Unsupported concepts are identified rather than improvised.

## Stage 3 — Complete learning loop

### P0 tasks

- Test-date and availability setup.
- Structured daily plan.
- Learn, Practice, Homework Help, Revision, and Test Preparation modes.
- Progressive hint policy.
- Independent mastery checks.
- Automatic future-plan adaptation.
- Parent diagnostic view.
- Final assessment and improvement report.

### Gate 3

- A child can complete the full flow without developer assistance.
- Plans contain executable sessions rather than generic prose.
- Guided success is not reported as independent mastery.
- Final evidence uses reviewed unseen items.
- Parents in usability testing understand the report without explanation.

## Stage 4 — Child safety and commercial pilot readiness

### P0 tasks

- Parent registration, consent, and child access.
- Privacy notice, terms, retention, export, and deletion.
- Safety policies and evaluation suite.
- Incorrect/unsafe answer reporting.
- Restricted and audited administrative investigation.
- Subscription or preparation-pass payment.
- Monitoring, support, and incident procedure.
- Pre-production smoke test and controlled production deployment.

### Gate 4

- Critical safety and prompt-injection tests pass.
- Export and deletion complete end-to-end.
- Production deployment and nested-route refresh tests pass.
- Administrators can investigate jobs and reports without unrestricted access.
- Billing and cancellation work.
- Qualified privacy/legal review identifies no unresolved launch blocker.

## Stage 5 — Concierge pilot

### Tasks

- Onboard 5 families manually.
- Review every mapping, plan, and final assessment.
- Observe child usage and interview participants.
- Measure baseline/final result and delayed retention when possible.
- Record support effort and AI cost.
- Ask for a second paid preparation period.

### Gate 5

Proceed to the 20-family pilot only when:

- at least 4 of 5 complete the diagnostic;
- at least 3 follow most of the plan;
- controlled final assessment shows improvement for most completers;
- no unresolved serious quality or safety incident exists;
- at least 3 families pay or make a credible payment commitment for another period.

## Stage 6 — Twenty-family paid pilot

### Tasks

- Onboard 20 qualified families with real upcoming assessments.
- Reduce manual intervention while preserving monitoring.
- Run weekly product and quality review.
- Compare against ordinary ChatGPT/Alice usage for a subset where practical.
- Collect parent, child, and teacher feedback.
- Test 99, 149, and 199 SEK preparation-pass pricing.

### Commercial go/no-go gate

Continue meaningful investment only if:

- 15+ learners complete the diagnostic;
- 10+ remain active through the preparation period;
- at least 50% of activated learners complete most planned sessions;
- reviewed pre/post evidence shows improvement for a clear majority of completers;
- at least 30% of engaged families pay or repurchase;
- at least 3 organic referrals or repeat purchases occur;
- the product is materially preferred over a general AI workflow by target families;
- serious incorrect-answer and safety rates are within an agreed threshold;
- delivery cost supports a credible gross margin;
- support effort can be reduced through product improvements.

## Decisions after the pilot

### Continue and deepen

When learning outcomes, retention, and payment are strong:

- improve Biology coverage;
- build the repeat-test and ongoing subscription experience;
- formalise teacher and tutoring-provider pilots;
- prepare non-dilutive funding and pre-seed evidence.

### Reposition

When students improve but parent payment is weak:

- test tutoring centres or schools as purchasers;
- test a teacher-reviewed assessment/reporting tool;
- test an older self-paying student segment.

### Stop

When usage, improvement, and payment remain weak after one disciplined correction cycle:

- do not add more subjects to mask the failure;
- preserve reusable document-learning technology;
- redeploy the backend toward a better-validated learning or professional-training problem.

## Expansion order after validation

No expansion is authorised by this strategy, but the candidate order after successful evidence is:

1. Additional Biology units.
2. History or Geography as the second theory-heavy subject.
3. Additional explanation/report languages based on actual parent concentration.
4. Tutoring-provider and independent-school workflows.
5. Chemistry and Physics after verification support improves.
6. Mathematics only after a dedicated symbolic and handwritten-work strategy.
7. India or UAE only after the Swedish acquisition and learning model is repeatable.

## Definition of MVP complete

The MVP is not complete when all planned features are deployed. It is complete when a real parent can pay, a real child can complete a preparation programme using real school material, controlled evidence shows what changed, and the business can decide rationally whether to continue.

