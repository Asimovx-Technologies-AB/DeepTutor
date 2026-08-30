# 03 — Product, AI, and Platform Plan

## A. Curriculum and pedagogy

### Curriculum model

- Convert the supported Lgr22 Biology scope into domains, topics, concepts, skills, prerequisites, and curriculum objectives.
- Maintain versioned Swedish terminology and English explanations.
- Record common misconceptions and suitable remediation for every supported concept.
- Define the expected depth and acceptable evidence for each learning dimension.
- Commission review by at least one qualified Swedish Biology teacher.

### Reviewed assessment bank

- Create approximately 150–200 reviewed items across the pilot concepts.
- Include multiple-choice, matching, terminology, short-answer, causal reasoning, comparison, diagram labelling, and application questions.
- Store correct answers, required elements, accepted alternatives, common incorrect answers, misconception mappings, difficulty, and estimated time.
- Use 20–30 adaptively selected items for an individual diagnostic.
- Reserve unseen items for the final assessment.

### Mastery model

- Store mastery state, confidence, last assessment, attempts, independent success, hints, misconceptions, evidence, and next review date.
- Distinguish exposure, guided success, immediate recall, independent application, and delayed retention.
- Do not increase mastery from passive reading or chat alone.
- Reassess prerequisites when a learner repeatedly struggles.
- Provide an understandable explanation for every parent-facing change.

## B. Parent and child experience

### Parent

- Register, verify email, authenticate, reset password, and manage subscription.
- Create and manage the child's minimal profile.
- Record informed consent and display child-appropriate privacy information.
- Configure grade, explanation language, test date, available days, and preferred session duration.
- View diagnostic findings, plan completion, concept changes, and final improvement.
- Export and delete data.

### Child

- Use a separate protected access flow without parent billing or report access.
- See one primary action: continue today's preparation.
- Pause and resume diagnostic or learning sessions.
- Receive clear, age-appropriate feedback without manipulative engagement mechanics.
- Report an incorrect, confusing, or unsafe answer.

## C. Material ingestion

- Support PDF and images first; include DOCX only when extraction is reliable.
- Validate file type, size, ownership, and malware risk.
- Extract page-level content, perform OCR, detect language and structure, and preserve source references.
- Identify the expected test scope from teacher instructions and study questions.
- Map content to supported curriculum concepts with confidence and evidence.
- Flag unsupported or low-quality material for clarification.
- Detect duplicate uploads.

### Durable job requirements

- Persist job state, stage, progress, timestamps, attempts, errors, and outputs.
- Continue after browser closure.
- Restore exact state after refresh.
- Support safe retry and cancellation.
- Make every stage idempotent.
- Prevent partially processed subjects from opening as blank pages.
- Give administrators a job timeline and actionable failure reason.

## D. Diagnostic and planning

### Diagnostic

- Explain duration and purpose before beginning.
- Start at an appropriate level and adapt difficulty and prerequisite checks.
- Accept “I don't know.”
- Save after every item.
- Avoid revealing answers during the diagnostic.
- Produce concept evidence and uncertainty, not an official grade.

### Study plan

- Represent plans and sessions as structured data, not generated prose.
- Prioritise foundational gaps and assessment scope.
- Fit sessions to the available days and remaining time.
- Combine explanation, guided practice, independent check, and spaced revision.
- Replan incomplete future sessions without altering history.
- Explain meaningful plan changes to the parent.

## E. AI tutoring

### Required modes

- Learn
- Practice
- Homework help
- Revision
- Final test preparation

### Interaction policy

- Begin from the session objective and current evidence.
- Ask what the child understands before giving a long explanation.
- Give one progressive hint at a time.
- Require an attempt before a final solution when appropriate.
- Detect likely misconceptions.
- Use correct Swedish Biology terms even when explaining in English.
- Cite uploaded sources where relevant.
- State uncertainty rather than fabricate.
- End with an independent item and a short session summary.

### Anti-cheating behaviour

- Identify likely homework requests.
- Ask for the student's attempt.
- Guide the next step instead of supplying an immediate final response.
- Provide a similar problem or question to check independent understanding.
- Never represent AI output as the student's own assessed work.

## F. AI and model architecture

- Isolate providers behind task-specific interfaces for tutoring, mapping, generation, evaluation, translation, safety, OCR/vision, and embeddings.
- Use the best suitable model per task rather than one model for everything.
- Use cheaper deterministic or smaller-model paths for classification and metadata.
- Store model, prompt, retrieval, curriculum, and rubric versions for every evaluated output.
- Implement timeouts, bounded retries, rate limits, provider fallback, and cost quotas.
- Prevent uploaded documents from overriding application policies.
- Minimise personal data sent to model providers.
- Disable provider training on customer data where configurable and contractually confirm data handling.

## G. Generated-content quality

Every generated assessment item must pass:

1. Supported-curriculum relevance.
2. Source and factual consistency.
3. Age and language appropriateness.
4. Answerability and ambiguity review.
5. Independent answer generation.
6. Rubric consistency.
7. Duplicate detection.
8. Safety review.

Unverified generated items must not be used as final improvement evidence.

## H. Parent reporting and outcome proof

### Parent dashboard

- Sessions planned and completed.
- Concepts addressed.
- Demonstrated improvement by learning dimension.
- Recurring misconceptions.
- Remaining gaps and confidence.
- Next session and final revision recommendation.

### Final report

- Baseline versus final performance on comparable unseen items.
- Concepts that moved and evidence supporting the change.
- Concepts still uncertain.
- Plan adherence.
- Limitations and disclaimer.
- Recommended follow-up.

## I. Safety, privacy, and compliance

- Parent-controlled child account and verifiable consent.
- Data minimisation and purpose limitation.
- Encryption in transit and at rest.
- Least-privilege access and audited administrative access.
- Documented retention, export, and end-to-end deletion.
- No advertising to children or sale of learning data.
- No model training on child content by default.
- Clear disclosure that the tutor is AI.
- Age-appropriate policies covering self-harm, abuse, bullying, sexual content, violence, drugs, eating disorders, discrimination, personal-information requests, emotional dependency, and prompt injection.
- Parent and child mechanisms for reporting an interaction.
- Legal/privacy review before a broad public launch.

## J. Operations and administration

- Development, pre-production/pilot, and production environments.
- EU-appropriate production data location for Swedish families.
- Repeatable deployments, safe migrations, compatibility checks, health/readiness probes, smoke tests, and rollback procedure.
- Admin functions for accounts, subscriptions, processing jobs, reported answers, safety events, curriculum versions, prompt/model versions, deletion, and support actions.
- Restricted conversation inspection with justification and audit trail.

## K. Measurement and evaluation

### Product metrics

- Registration-to-child-profile conversion.
- Upload and diagnostic completion.
- Time to first usable plan.
- Weekly active learners.
- Planned versus completed sessions.
- Four-week retention.
- Trial-to-paid conversion.
- Repeat test-preparation purchase.

### Learning metrics

- Baseline/final change on reviewed unseen items.
- Delayed retention.
- Independent versus hinted success.
- Concept and misconception changes.
- Parent and teacher agreement with reported gaps.

### Operational metrics

- Processing completion and duration.
- Stuck and retried jobs.
- Tutor latency and provider errors.
- Incorrect-answer and safety-report rates.
- Cost per processed test workspace.
- Cost per active learner and completed preparation period.

### AI evaluation suite

Maintain a versioned benchmark covering Swedish terminology, factual correctness, source grounding, curriculum mapping, misconception detection, tutoring quality, rubric evaluation, safety, prompt injection, latency, and cost.

