# DeepTutor agent and contributor contract

These instructions apply to the whole repository. Preserve existing behaviour
unless the task explicitly authorizes a change.

## Sources of truth

- Application behaviour: executable code and tests.
- Deployed development infrastructure: `infra/terraform/` and
  `.github/workflows/`.
- Official Windows developer setup: `compose.yml`,
  `backend/.env.canonical-local.example`, `scripts/dev-setup.ps1`, and
  `documentation/development/local-windows-setup.md`.
- Product intent and delivery scope: current documents under
  `documentation/mvpstrategy/` and `documentation/strategy/`.

Older top-level documents may describe SQLite, ChromaDB, FAISS, Ollama, Neon,
Pinecone, Render, or Netlify. Treat them as historical or optional unless the
current code and the sources above confirm otherwise.

## Architecture boundaries

- PostgreSQL plus pgvector is the canonical data profile for deployable work.
- Azure is the deployed development platform. Developers may run local
  substitutes, but local success does not override Azure acceptance.
- Azure AI Foundry/Azure OpenAI is the canonical AI validation provider. Chat
  provider and model selection must remain configurable; Ollama and Gemini are
  supported local alternatives where the existing adapters support them.
- Keep business and learning-domain logic independent of cloud vendors, model
  names, vector stores, and local filesystem paths.
- Access LLMs, embeddings, vector stores, graph stores, and durable file stores
  through their configured adapters. Do not add direct provider calls to API or
  domain code when an adapter is available.
- Do not silently fall back to a different database or provider in canonical
  tests. Fail clearly when a required dependency is unavailable.
- Never assume embeddings from different providers are interchangeable.
  Dimension/model changes require an explicit schema and re-indexing strategy.
- New schema changes should move toward a reviewed PostgreSQL migration
  mechanism. Do not expand ad-hoc startup `ALTER TABLE` logic without first
  reporting the architectural issue.

## Change discipline

- Do not perform broad refactoring merely because a cleaner architecture is
  possible.
- If existing design creates correctness, security, data-loss, scalability, or
  provider-compatibility risk, explain the evidence and proposed migration
  before making a wide change.
- Small, necessary safety fixes may accompany a scoped task when they are
  covered by tests and called out explicitly.
- Preserve unrelated work in a dirty worktree. Never rewrite or discard changes
  that are outside the task.
- Do not hard-code secrets, Azure resource URLs, deployment names, credentials,
  or developer-specific absolute paths.

## Validation expectations

- Backend changes: run the relevant pytest suite and PostgreSQL/pgvector checks
  when persistence or retrieval is affected.
- Frontend changes: run `npm run lint` and `npm run build`.
- Infrastructure changes: format and validate Terraform and inspect the plan;
  never apply or destroy infrastructure without explicit authorization.
- Documentation-only changes: verify paths, commands, configuration names, and
  links against the repository.
- A feature developed with an optional local provider is merge-ready only when
  its provider-independent behaviour passes the canonical compatibility gate.
