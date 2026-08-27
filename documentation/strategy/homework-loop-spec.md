# Homework Loop — Technical Spec (v1 draft)

*Drafted 27 Aug 2026. Implements the flagship differentiation feature from
differentiation.md. Phased: "Family lite" ships in MVP-2, "Classroom" in MVP-3.*

## Roles

Extend `User` (`backend/app/core/models.py`) with:

```
role: str  # "student" | "parent" | "teacher"  (default "student")
```

Existing accounts default to `student`. Auth stays as-is (JWT); role lands in
the token claims so the frontend can route to the right home view.

## New models

```
ParentChildLink
  id            uuid pk
  parent_id     fk users.id
  child_id      fk users.id
  status        "pending" | "active" | "revoked"   # child or parent can revoke
  created_at    datetime
  # unique (parent_id, child_id); a child may have multiple parents

Class                                   # MVP-3 only
  id            uuid pk
  teacher_id    fk users.id
  name          str
  invite_code   str unique              # students join by code, no email needed

ClassMembership                         # MVP-3 only
  id            uuid pk
  class_id      fk classes.id
  student_id    fk users.id

Assignment
  id            uuid pk
  creator_id    fk users.id             # parent (MVP-2) or teacher (MVP-3)
  student_id    fk users.id nullable    # direct assignment (Family)
  class_id      fk classes.id nullable  # class assignment (Classroom); exactly one of the two set
  title         str
  kind          "quiz" | "reading" | "flashcards"
  document_id   fk documents.id nullable   # grounding material
  topic_id      str nullable
  quiz_id       fk quizzes.id nullable  # generated on creation via existing quiz engine
  due_at        datetime
  pass_threshold float                  # e.g. 0.7
  socratic_lock bool default true       # tutor hints only, no answers, while active
  created_at    datetime

AssignmentAttempt
  id            uuid pk
  assignment_id fk assignments.id
  student_id    fk users.id
  quiz_attempt_id fk quiz_attempts.id nullable   # reuses existing QuizAttempt
  time_on_task_seconds int              # accumulated from heartbeat pings
  status        "not_started" | "in_progress" | "submitted" | "passed" | "failed"
  submitted_at  datetime nullable

SignOff
  id            uuid pk
  attempt_id    fk assignment_attempts.id
  parent_id     fk users.id
  method        "tap"                   # "bankid" reserved for a future migration
  note          str nullable            # optional parent comment
  signed_at     datetime
```

All via Alembic migrations (introduced in MVP-1 foundation work) — no more
try/except `ALTER TABLE`.

## API surface (new router `api/assignments.py`)

```
POST   /api/links                    parent invites child (email or code); child accepts
DELETE /api/links/{id}               revoke
POST   /api/assignments              create (parent MVP-2 / teacher MVP-3); generates quiz via existing engine
GET    /api/assignments?role=...     student: my tasks; parent: children's tasks; teacher: class view
POST   /api/assignments/{id}/start   creates attempt, starts time tracking
POST   /api/assignments/{id}/heartbeat   time-on-task ping (throttled, e.g. 60s)
POST   /api/assignments/{id}/submit  links QuizAttempt, computes pass/fail
POST   /api/attempts/{id}/signoff    parent only; validated against ParentChildLink
GET    /api/digest/weekly            parent digest data (also emailed)
```

## Socratic mode

When a chat request carries an active `assignment_id` with `socratic_lock`:

- The chat prompt template switches to a Socratic variant: explain concepts,
  ask guiding questions, give worked *analogous* examples — never the answer to
  the assigned questions.
- The retrieval layer excludes the assignment's own quiz answer content from
  context.
- Add a RAGAS-style eval case set for "does Socratic mode leak answers" — this
  gate runs in CI like the other answer-quality evals.

Prompt work + one retrieval filter; no new AI infrastructure.

## Verification signals (v1 — keep it honest but simple)

- Time-on-task from heartbeats (floor threshold per assignment kind)
- Score vs. `pass_threshold` from the existing quiz engine
- Attempt count
- Optional "explain it back": one free-text question graded by the existing
  hallucination-guard/grading path, answered with Socratic chat disabled

Explicitly **not** in v1: webcam/proctoring of any kind, keystroke analysis.
Trust posture is "verified effort," not surveillance — this matters for the
Swedish market especially.

## Notifications

- MVP-2: email only (assignment created, due tomorrow, submitted → parent,
  sign-off done → student). Provider: any transactional email service; template
  strings go through the existing translations system (en/sv/ar ready).
- Later: web push; WhatsApp for the India institute channel (institutes ask for
  it; evaluate cost then).

## Frontend additions

- Parent home: children list, pending sign-offs, weekly digest view
- Student: "My tasks" list + task-mode chat (Socratic banner visible — the
  student should *know* answers are locked; it reframes the tool as fair)
- Teacher (MVP-3): class roster, assignment composer, completion dashboard
- Reuse existing quiz/flashcard components; new screens are CRUD + lists

## Effort estimate

| Slice | Estimate |
|---|---|
| Models + migrations + links API | 3–4 days |
| Assignments API + verification | 4–5 days |
| Socratic mode + eval cases | 3–4 days |
| Parent/student UI | 5–6 days |
| Digest + email | 3 days |
| **Family lite total (MVP-2)** | **~3–4 weeks** |
| Classroom additions (class entities, teacher UI, dashboard) | ~2–3 weeks in MVP-3 |

## Open questions for sprint planning

1. Child accounts for under-13s: parent-created accounts (no child email) —
   needed for GDPR/consent anyway. Decide the minimum-age flow.
2. Does a parent see chat transcripts or only summaries? Recommendation:
   summaries only by default — teen trust is retention; make transcript access
   an explicit, visible-to-student setting.
3. BankID integration cost/benefit — only if a Swedish pilot demands it.
