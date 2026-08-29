# ─────────────────────────────────────────────────────────────────────────────
# Core identity of the deployment
# ─────────────────────────────────────────────────────────────────────────────
variable "subscription_id" {
  description = "Azure subscription ID. Prefer the ARM_SUBSCRIPTION_ID env var in CI."
  type        = string
  default     = null
}

variable "project" {
  description = "Short project slug used in every resource name. Lowercase alphanumeric."
  type        = string
  default     = "deeptutor"

  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.project))
    error_message = "project must be 3-12 lowercase alphanumeric characters (it seeds globally unique names)."
  }
}

variable "environment" {
  description = "Environment slug. One resource group is created per environment."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "stg", "prod"], var.environment)
    error_message = "environment must be one of: dev, stg, prod."
  }
}

variable "location" {
  description = "Primary Azure region. Central India keeps the API, database, storage and observability close to DeepTutor's Indian users."
  type        = string
  default     = "centralindia"
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}

# ─────────────────────────────────────────────────────────────────────────────
# Container Apps — the API (and optional background worker)
# ─────────────────────────────────────────────────────────────────────────────
variable "container_image" {
  description = <<-EOT
    Image the API container app starts with. Left at the public quickstart image
    so `terraform apply` succeeds before the first backend build exists; after
    that the deploy-backend workflow owns the tag and Terraform ignores changes
    to it (see lifecycle block in container_apps.tf).
  EOT
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}

variable "api_cpu" {
  description = "vCPU per API replica. 0.5 runs the slim image comfortably."
  type        = number
  default     = 0.5
}

variable "api_memory" {
  description = "Memory per API replica. Must pair with api_cpu per the ACA CPU/memory table (0.5 -> 1Gi)."
  type        = string
  default     = "1Gi"
}

variable "api_min_replicas" {
  description = <<-EOT
    0 = scale to zero. Dev default: the Consumption free grant makes an idle
    environment effectively free, at the cost of a cold start on first request.
    Set to 1 for a demo-able always-warm API (~USD 33/mo at 0.5 vCPU / 1Gi).
  EOT
  type        = number
  default     = 0
}

variable "api_max_replicas" {
  description = "Upper bound on API replicas. Also the cost ceiling under load."
  type        = number
  default     = 2
}

variable "enable_worker" {
  description = <<-EOT
    Deploy the ARQ indexing worker as a second container app.
    Keep false until backend/app/worker.py exists — see the report's Phase 3.
  EOT
  type        = bool
  default     = false
}

variable "allowed_cors_origins" {
  description = "Origins the API accepts. Empty list means 'the Static Web App hostname only', wired automatically."
  type        = list(string)
  default     = []
}

# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL Flexible Server — relational data + pgvector + graph JSONB
# ─────────────────────────────────────────────────────────────────────────────
variable "postgres_sku_name" {
  description = "B_Standard_B1ms is the cheapest burstable tier that runs pgvector fine at beta scale."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "postgres_storage_mb" {
  description = "Storage in MB. 32768 (32 GiB) is the floor; storage cannot be shrunk later."
  type        = number
  default     = 32768
}

variable "postgres_version" {
  description = "Major PostgreSQL version."
  type        = string
  default     = "16"
}

variable "postgres_admin_username" {
  description = "Server admin login."
  type        = string
  default     = "dtadmin"
}

variable "postgres_backup_retention_days" {
  description = "Retained backups. 7 days is included in the price."
  type        = number
  default     = 7
}

variable "postgres_allowed_ips" {
  description = <<-EOT
    Map of label => { start, end } public IPs allowed to reach Postgres, for
    psql/migrations from a laptop or CI. Container Apps reach it through the
    'AllowAzureServices' rule, not this list. Keep it short and reviewed.
  EOT
  type = map(object({
    start = string
    end   = string
  }))
  default = {}
}

# ─────────────────────────────────────────────────────────────────────────────
# Optional Azure OpenAI (off by default: Gemini is the current provider)
# ─────────────────────────────────────────────────────────────────────────────
variable "enable_azure_openai" {
  description = <<-EOT
    Provision an Azure OpenAI account with chat + embedding deployments.
    S0 is pay-per-token, so an unused account costs nothing — but switching
    embeddings means re-indexing every document. Read the report first.
  EOT
  type        = bool
  default     = false
}

variable "azure_openai_location" {
  description = "Region for the Azure OpenAI account; model availability differs from var.location."
  type        = string
  default     = "southindia"
}

variable "azure_openai_chat_model" {
  description = "Chat model deployed when enable_azure_openai is true."
  type = object({
    name     = string
    version  = string
    capacity = number
  })
  default = {
    name     = "gpt-4.1-mini"
    version  = "2025-04-14"
    capacity = 10 # x1000 TPM — keeps the dev spend bounded
  }
}

variable "azure_openai_embedding_model" {
  description = "Embedding model deployed when enable_azure_openai is true."
  type = object({
    name     = string
    version  = string
    capacity = number
  })
  default = {
    name     = "text-embedding-3-small"
    version  = "1"
    capacity = 10
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# Observability
# ─────────────────────────────────────────────────────────────────────────────
variable "log_daily_quota_gb" {
  description = "Hard daily ingestion cap on Log Analytics. The single most effective guard against a surprise bill."
  type        = number
  default     = 0.5
}

variable "log_retention_days" {
  description = "Log retention. 30 days is the free floor."
  type        = number
  default     = 30
}

# ─────────────────────────────────────────────────────────────────────────────
# Frontend
# ─────────────────────────────────────────────────────────────────────────────
variable "static_web_app_location" {
  description = <<-EOT
    Static Web Apps is offered in a small set of regions and has no India
    deployment location, so the SPA is pinned to East Asia, the closest
    supported option in this provider configuration. Static assets are served
    through the global edge network, and the SPA holds no personal data.
  EOT
  type        = string
  default     = "eastasia"

  validation {
    condition = contains(
      ["westus2", "centralus", "eastus2", "westeurope", "eastasia"],
      var.static_web_app_location,
    )
    error_message = "static_web_app_location must be a region where Static Web Apps is available."
  }
}
