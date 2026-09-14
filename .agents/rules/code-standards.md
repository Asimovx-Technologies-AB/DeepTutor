# Code Standards & Quality Rules

## 1. No Hardcoding
- **Zero Hardcoded Domain Logic**: Never hardcode topic names, dataset keys, or specific academic answers into general business or tutoring logic. Code must generalize to any uploaded document or curriculum.
- **Configuration & Secrets**: Keep API keys, connection strings, hostnames, ports, and model names in environment variables or configuration files (`.env`, `config.py`).
- **Dynamic Adaptability**: Derive schemas, dimensions, and chunk limits dynamically from models or metadata rather than hardcoding magic numbers.

## 2. Architecture & Data Boundaries
- **Canonical Storage**: PostgreSQL + pgvector is the canonical data store.
- **Provider Independence**: Keep business and learning-domain logic independent of cloud vendors, model names, and vector stores. Access AI services via configured adapters.
- **Fail Clearly**: Do not silently fallback to unrelated providers or empty data. Log informative errors with actionable context.

## 3. Change Discipline & Validation
- **Preserve Dirty Worktree**: Never overwrite or revert unrelated changes in the working tree.
- **Scoped Tasks**: Make targeted, minimal changes that solve the user's explicit request. Avoid unsolicited broad refactoring.
- **Test Before Declaring Complete**: Always run test suites (e.g. `pytest` for backend, `npm run build` / `npm run lint` for frontend) and verify execution before concluding the task.
