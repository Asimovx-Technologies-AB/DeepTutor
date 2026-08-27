# Differentiation: Beating the Free Tools

*Drafted 27 Aug 2026. The standing fear this doc answers: "I can do that in
ChatGPT."*

## The moat filter

We will never out-chat ChatGPT/Claude. Any feature shaped like *"ask a question
→ get an answer"* is replicable in a free tab and is dead on arrival. Every
roadmap feature must pass at least one of these two tests:

1. **Multi-person** — it involves more than one human (teacher–student–parent
   workflows, class-shared material, sign-offs, dashboards). Chat tools are
   single-player by design.
2. **Stateful over time, and it acts on that state** — it knows what the student
   was supposed to master by when, what they got wrong three weeks ago, that the
   exam is in 41 days — and it *does something* about it (schedules, nags,
   re-plans, reports). A chat window holds a conversation, not a curriculum.

Third structural advantage, market-specific: **for schools, free ChatGPT is not
a legal competitor** (GDPR/Schrems II; several Swedish kommuner have restricted
it) — and teachers see it as the cheating tool.

## Positioning

> **ChatGPT helps students fake their homework. DeepTutor proves they actually
> did it.**

We are not a better chatbot; we are the accountability and verified-learning
layer that the free tools created the need for.

## Flagship: the homework / parent sign-off loop

Origin: Swedish läxa practice — homework that parents must sign off on. The
workflow (full spec in homework-loop-spec.md):

1. **Teacher (or parent) assigns**: material + auto-generated quiz/reading task
   + due date + pass threshold.
2. **Student completes at home** with the AI tutor in **Socratic mode** — it
   hints, explains, and asks guiding questions but refuses to hand over answers
   for assigned work. This is the anti-ChatGPT guarantee.
3. **System verifies real work**: time-on-task, attempts, score vs. threshold,
   optional "explain it back" check answered unaided.
4. **Parent gets a plain-language summary** ("25 min, 8/10, struggled with
   equations") and signs off with one tap. BankID later in Sweden for
   legal-grade sign-off.
5. **Teacher sees a class dashboard**: who's done, who's stuck, where the class
   is weak.

**One engine, three markets**: Sweden = läxa sign-off; India = automated parent
report card (huge for coaching-institute deals); UAE = tutoring-center
accountability loop.

**Feasibility: high.** The AI-hard parts exist (quiz generation, grounded
tutoring, `QuizAttempt`/`UserProgress` storage). New work is conventional web
dev: roles, assignment entities, parent linking, notifications, two dashboards.
~3–4 weeks for v1. The hard part is UX and trust, not tech.

## Other features that pass the filter

| Feature | Why chat can't copy it |
|---|---|
| Spaced repetition that chases the student (SM-2 over existing flashcards + notifications) | ChatGPT will never text a kid about what they failed last Friday |
| Weak-area-driven quiz generation (progress data biases the quiz engine) | Requires longitudinal per-student data |
| Class-shared grounding (one teacher upload serves 30 students; answers cite the class textbook's pages and use the teacher's method) | Multi-user shared context; persistent 500-page corpus per class |
| Exam-countdown orchestration (study plan re-plans around slippage) | Acting on state over time |
| Sovereign school deployment (fully local Ollama/FAISS mode) | OpenAI/Google structurally won't ship this |
| Scanned-PDF pipeline (VLM parsing of photocopied coaching notes) | Free tiers choke on scanned material at textbook scale |

## What fails the filter (deprioritize)

Marginally better chat answers; general "ask me anything" polish; the MCP
drawer as a user-facing feature; any feature whose demo is indistinguishable
from pasting into ChatGPT.

## Guardrail for every sprint planning session

Before committing to a feature, ask: *"Could a motivated student get 90% of
this from a free ChatGPT tab?"* If yes, it must either be cut or reframed until
it passes the moat filter.
