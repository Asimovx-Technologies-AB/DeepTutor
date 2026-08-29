# DeepTutor infrastructure

Terraform for the whole DeepTutor platform on Azure. Everything for one
environment lands in a single resource group (`rg-deeptutor-dev`); Terraform
state lives in its own group so a `destroy` cannot eat it.

The reasoning behind every choice — SKUs, costs, what has to change in the
application code — is in
[`documentation/strategy/azure-deployment.md`](../documentation/strategy/azure-deployment.md).
Read that first. This file is the runbook.

```
infra/
  bootstrap/          run once per subscription: creates the state storage
  terraform/          the configuration itself
    envs/dev.tfvars   the dev-tier settings (cheapest working shape)
```

## What gets created

| Resource | Name | Purpose |
|---|---|---|
| Resource group | `rg-deeptutor-dev` | Everything below |
| Container Apps env + app | `cae-…`, `ca-deeptutor-dev-api` | FastAPI backend |
| Static Web App | `stapp-deeptutor-dev` | React SPA (Free tier) |
| PostgreSQL Flexible Server | `psql-deeptutor-dev` | Relational data, pgvector, graph JSONB |
| Storage account | `st…` | Blob containers + Azure Files mounts |
| Container registry | `cr…` | API image (Basic) |
| Key Vault | `kv-…` | DB URL, JWT key, third-party API keys |
| Log Analytics + App Insights | `log-…`, `appi-…` | Logs and traces, capped at 0.5 GB/day |
| User-assigned identity | `id-deeptutor-dev` | ACR pull, Key Vault read, Blob write |
| Azure OpenAI *(optional)* | `oai-…` | Off by default — see report §6.4 |

## First-time setup

### 1. State storage

```bash
cd infra/bootstrap
./bootstrap.sh <subscription-id>
```

(Windows: `./bootstrap.ps1 -SubscriptionId <subscription-id>`.)

Copy the printed storage account name into
`infra/terraform/envs/dev.backend.hcl`.

### 2. CI identity

GitHub Actions authenticates with OIDC federation — no client secret is ever
created or stored.

```bash
APP_ID=$(az ad app create --display-name "github-deeptutor-infra" --query appId -o tsv)
az ad sp create --id "$APP_ID"
OBJ_ID=$(az ad app show --id "$APP_ID" --query id -o tsv)
```

Federate the three trust subjects the workflows use — `main`, pull requests,
and the `dev` environment:

```bash
for SUBJECT in \
  "repo:<org>/DeepTutor:ref:refs/heads/main" \
  "repo:<org>/DeepTutor:pull_request" \
  "repo:<org>/DeepTutor:environment:dev" \
  "repo:<org>/DeepTutor:environment:dev-plan"
do
  az rest --method POST \
    --uri "https://graph.microsoft.com/v1.0/applications/${OBJ_ID}/federatedIdentityCredentials" \
    --body "{\"name\":\"$(echo "$SUBJECT" | tr ':/' '--')\",\"issuer\":\"https://token.actions.githubusercontent.com\",\"subject\":\"${SUBJECT}\",\"audiences\":[\"api://AzureADTokenExchange\"]}"
done
```

Grant it rights on the subscription. `Contributor` creates the resources;
`User Access Administrator` is needed because Terraform also creates the role
assignments that let the app identity read Key Vault and pull from ACR:

```bash
SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
for ROLE in "Contributor" "User Access Administrator"; do
  az role assignment create --assignee-object-id "$SP_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "$ROLE" --scope "/subscriptions/<subscription-id>"
done
```

The `azurerm` backend uses Microsoft Entra authentication for the state blob.
`Contributor` does not grant blob data-plane access, so grant that separately
on the state storage account printed by the bootstrap script:

```bash
STATE_ID=$(az storage account show \
  --resource-group rg-deeptutor-tfstate \
  --name <state-storage-account> \
  --query id -o tsv)
az role assignment create \
  --assignee-object-id "$SP_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STATE_ID"
```

> Scope both roles to the two resource groups instead of the subscription once
> they exist, if your tenant's policy calls for it. Subscription scope is only
> needed for the very first apply.

### 3. GitHub configuration

Repository **variables** (not secrets — none of these are sensitive):

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | the `$APP_ID` above |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | your subscription |
| `TFSTATE_RESOURCE_GROUP` | from bootstrap output |
| `TFSTATE_STORAGE_ACCOUNT` | from bootstrap output |
| `TFSTATE_CONTAINER` | `tfstate` |

Create two GitHub **Environments**: `dev` (add required reviewers — this is the
approval gate before anything is applied or deployed) and `dev-plan` (no
reviewers; it only ever runs `terraform plan`).

### 4. First apply

Run the **infra-apply** workflow manually, or merge a change under
`infra/terraform/`. The API starts on a public placeholder image; the real
image arrives with the first backend deploy.

### 5. Choose the RAG provider

The safe default keeps the legacy Gemini + Pinecone path until Azure OpenAI
quota is confirmed. To use the Azure-native path, set this in `envs/dev.tfvars`:

```hcl
enable_azure_openai = true
```

That single toggle configures the application for Azure OpenAI chat and
1,536-dimensional embeddings, PostgreSQL pgvector, and managed-identity
authentication. On first use, the backend creates the `vector` extension and
`document_chunks` schema. Existing Pinecone vectors are not copied: re-index
the source documents before directing test users to the environment.

### 6. Populate legacy secrets only when required

When `enable_azure_openai = false`, Terraform creates legacy secret slots so no
API key is ever in a `.tfvars` file or in Terraform state:

```bash
KV=$(az keyvault list -g rg-deeptutor-dev --query "[0].name" -o tsv)
az keyvault secret set --vault-name "$KV" --name GEMINI-API-KEY   --value "..."
az keyvault secret set --vault-name "$KV" --name PINECONE-API-KEY --value "..."
az keyvault secret set --vault-name "$KV" --name SERPER-API-KEY   --value "..."
az keyvault secret set --vault-name "$KV" --name OPENAI-API-KEY   --value "..."
```

Secrets are referenced versionlessly, so a rotated value is picked up by the
next revision without a Terraform run.

When Azure-native mode is enabled, these third-party secret slots are not
created. Azure OpenAI uses the Container App's managed identity.

### 7. Deploy

Push to `main` under `backend/**` or `frontend/**`, or run **deploy-backend** /
**deploy-frontend** manually. Backend first — the frontend build reads the live
API hostname.

## Working locally

```bash
cd infra/terraform
terraform init -backend-config=envs/dev.backend.hcl
terraform plan -var-file=envs/dev.tfvars
```

`terraform fmt -recursive` before committing; CI fails on unformatted files.

## Cost controls

- `api_min_replicas = 0` — the API scales to zero and the Container Apps free
  grant covers an idle dev environment. Set it to `1` for an always-warm demo
  and expect roughly USD 33/month more.
- `log_daily_quota_gb = 0.5` — a hard ingestion cap, the single most effective
  guard against a surprise bill.
- Postgres is the only resource that bills around the clock (~USD 16/month).
  It can be stopped for up to 7 days at a time:
  `az postgres flexible-server stop -g rg-deeptutor-dev -n psql-deeptutor-dev`.
- Tear the whole environment down with the **infra-apply** workflow and the
  `destroy` input checked. `prevent_destroy` on the Postgres *database* is
  deliberate: dropping it needs a conscious edit.

## Known gaps

Tracked in the report, not silently:

- `enable_worker = false` — the ARQ worker has no `app/worker.py` yet, and no
  Redis is provisioned. Report §6.3.
- Azure-native RAG is feature-gated by `enable_azure_openai`; quota and model
  availability must be confirmed before enabling it. Pinecone and Gemini stay
  available as a rollback path until re-indexing and retrieval benchmarks pass.
- The API allows CORS from `*` in code and ignores `CORS_ALLOWED_ORIGINS`.
  Report §4.4 — fix this before the environment is shared.
- The graph store writes JSON to an Azure Files mount. That stops the data
  loss; moving it into Postgres JSONB is the real fix. Report §6.2.
