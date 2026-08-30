# Windows local development setup

This is the supported local-development path for DeepTutor. It keeps the data
layer compatible with the deployed Azure development environment while allowing
developers to choose a chat model suitable for their machine and access.

## Architecture contract

| Concern | Canonical local value | Reason |
|---|---|---|
| Relational database | PostgreSQL 16 in Docker Desktop | Matches Azure PostgreSQL semantics |
| Vector store | pgvector | Prevents features being built only for ChromaDB or FAISS |
| Embeddings | Azure AI Foundry deployment, 1,536 dimensions | Matches the deployed vector schema |
| Chat model | Azure AI Foundry, Ollama, or Gemini | Chat is provider-selectable behind the existing client |
| Files and graph data | Local directories | Simple local substitute for Azure-mounted durable storage |

The Azure AI Foundry deployment is the **canonical validation provider**, not
the only permitted chat provider. A developer may use another supported chat
model locally. Completion still requires the PostgreSQL/pgvector checks and a
canonical Azure-development smoke test.

## Prerequisites

- Windows 11 with PowerShell 7 recommended
- Docker Desktop using Linux containers
- Python 3.11, including the Windows `py` launcher
- Node.js 22 and npm
- Azure CLI only when using Azure AI Foundry without an API key
- Ollama only when choosing a local Ollama chat model

## First-time setup

From the repository root:

```powershell
.\scripts\dev-setup.ps1
.\scripts\dev-check.ps1
```

The setup starts PostgreSQL/pgvector, creates `backend/.env` from the canonical
template if it does not already exist, creates the backend virtual environment,
installs backend dependencies, and runs `npm ci` for the frontend. Existing
`backend/.env` files are never overwritten.

To start only infrastructure and generate configuration:

```powershell
.\scripts\dev-setup.ps1 -SkipDependencies
```

## Select a chat provider and model

Provider and model selection is configuration, not a code change. Edit the
uncommitted `backend/.env` file.

### Azure AI Foundry / Azure OpenAI — canonical

```env
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://<resource-name>.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4.1-mini
```

The value is an Azure **deployment name**, which may point to any compatible
model deployed for the project. Authenticate without storing a key:

```powershell
az login
```

The developer needs permission to invoke the deployment. An API key is also
supported locally but must remain in `backend/.env` and must never be committed.

### Ollama — local chat

```powershell
.\scripts\dev-setup.ps1 -ChatProvider ollama
ollama pull llama3.1
```

Or update an existing `backend/.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=llama3.1
```

Any installed Ollama chat model can be selected. Keep
`EMBEDDING_PROVIDER=azure_openai` for deployment-compatible pgvector data.

### Gemini — alternative chat

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=<local-secret>
GEMINI_CHAT_MODEL=gemini-flash-latest
```

Gemini currently falls back to Ollama when unavailable. Do not rely on that
fallback in tests; make the intended provider explicit.

## Start the application

Backend terminal:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Frontend terminal:

```powershell
Set-Location frontend
npm run dev
```

Open `http://localhost:5173`. API documentation is at
`http://localhost:8000/docs`, and health information is at
`http://localhost:8000/api/health`.

## Changing the embedding provider

Chat models can be changed freely because chat output is not stored in the
vector column. Embedding providers are different:

| Provider | Current dimensions |
|---|---:|
| Azure OpenAI / OpenAI | 1,536 |
| Ollama | 768 |
| Gemini | 3,072 |

Changing the embedding provider changes vector dimensions and requires a
separate compatible schema plus document re-indexing. Gemini's 3,072-dimensional
vectors also exceed the current pgvector HNSW index limit enforced by the
application. Therefore alternative embeddings are experimental and are not
part of the canonical local profile.

Do not change `EMBEDDING_PROVIDER`, `PGVECTOR_DIMENSIONS`, or the deployed
embedding model merely to select a different **chat** model.

## Useful commands

```powershell
docker compose stop
docker compose up -d postgres
docker compose logs postgres
.\scripts\dev-check.ps1
```

Removing the Docker volume deletes the local database and is intentionally not
part of the setup scripts. If a clean database is genuinely needed, resolve the
exact `deeptutor-local` volume in Docker Desktop and delete it deliberately.

## Definition of done

A backend feature is not complete because it works with SQLite, ChromaDB,
FAISS, Ollama, or Gemini alone. Before merge it must:

1. pass unit tests;
2. start with PostgreSQL fallback disabled;
3. pass PostgreSQL/pgvector integration checks;
4. avoid provider-specific logic outside provider/storage adapters;
5. be smoke-tested in the deployed Azure development environment when it
   changes an integration path.

The older SQLite/FAISS/ChromaDB/Ollama combination remains an optional offline
and experimentation profile. It is not the acceptance environment.
