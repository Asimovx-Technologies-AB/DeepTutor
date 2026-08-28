locals {
  # `deeptutor-dev`, `deeptutordev` — the two shapes Azure naming rules need.
  name        = "${var.project}-${var.environment}"
  name_compact = "${var.project}${var.environment}"

  tags = merge(
    {
      project     = var.project
      environment = var.environment
      managed_by  = "terraform"
      repo        = "DeepTutor"
    },
    var.tags,
  )

  # Storage account and ACR names are globally unique and alphanumeric-only,
  # so they get a deterministic suffix derived from subscription + name.
  unique_suffix = substr(sha1("${data.azurerm_client_config.current.subscription_id}-${local.name}"), 0, 6)

  storage_account_name = substr("st${local.name_compact}${local.unique_suffix}", 0, 24)
  acr_name             = substr("cr${local.name_compact}${local.unique_suffix}", 0, 50)
  key_vault_name       = substr("kv-${local.name}-${local.unique_suffix}", 0, 24)

  postgres_database_name = "deeptutor"

  # CORS: the SPA origin unless the operator pinned an explicit list.
  cors_origins = length(var.allowed_cors_origins) > 0 ? var.allowed_cors_origins : [
    "https://${azurerm_static_web_app.frontend.default_host_name}"
  ]

  # Third-party keys Terraform creates as empty placeholders and never reads.
  # Values are written out-of-band (az keyvault secret set / GitHub workflow),
  # so no API key ever lands in state or in a .tfvars file.
  external_secret_names = [
    "GEMINI-API-KEY",
    "OPENAI-API-KEY",
    "SERPER-API-KEY",
    "PINECONE-API-KEY",
  ]
}
