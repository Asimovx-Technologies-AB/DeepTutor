# Plan, Build, and Test Checklist

Use this checklist during every coding or refactoring task to ensure production quality.

---

### Phase 1: Planning
- [ ] Understand user intent and explicit constraints (e.g. "no hardcoding", "support streaming").
- [ ] Inspect existing architecture and active database/adapter layers before touching code.
- [ ] Formulate a step-by-step approach covering:
  - Data ingestion / parameter flow
  - Error and edge case handling
  - Verification strategy

---

### Phase 2: No Hardcoding Audit
- [ ] No hardcoded domain terms or academic answers in search or prompting layers.
- [ ] No inline credentials, API keys, or raw tokens.
- [ ] No hardcoded file system paths (`C:\...`, `/tmp/...`). Use dynamic workspace paths or configs.
- [ ] No hardcoded model names or vector dimensions in general business logic.
- [ ] Configurable timeouts, batch sizes, and thresholds passed via parameters or environment.

---

### Phase 3: Production-Grade Code
- [ ] Explicit type annotations (`typing.Optional`, `typing.List`, `typing.Dict`, Pydantic models).
- [ ] Informative error logging with traceback and context instead of silent `pass` or generic `except Exception:`.
- [ ] Clean separation of concerns (controller vs. service vs. adapter).
- [ ] Docstrings explaining *why* decisions were made, not merely repeating code keywords.

---

### Phase 4: Verification Gate
- [ ] Run targeted unit / integration tests (e.g. `pytest backend/tests/...`).
- [ ] Test at least one boundary/edge case (e.g. empty input, query yielding 0 immediate matches, network blip).
- [ ] Ensure frontend compiles cleanly (`npm run build`) if frontend files were modified.
- [ ] Verify that live runtime logs show successful execution without errors or regressions.
