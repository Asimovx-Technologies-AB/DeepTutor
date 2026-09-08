locals {
  # `deeptutor-dev`, `deeptutordev` — the two shapes Azure naming rules need.
  name         = "${var.project}-${var.environment}"
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

  # CORS: the SPA's origins. The Static Web App default hostname is wired in
  # automatically, but a custom domain fronting the same SPA is a *separate*
  # browser origin and Terraform does not provision it, so it has to be named
  # in frontend_custom_domains. An explicit allowed_cors_origins still replaces
  # the whole list.
  cors_origins = length(var.allowed_cors_origins) > 0 ? var.allowed_cors_origins : concat(
    ["https://${azurerm_static_web_app.frontend.default_host_name}"],
    [for domain in var.frontend_custom_domains : "https://${domain}"]
  )

  # The Azure-native path authenticates to Azure OpenAI with managed identity
  # and pgvector with DATABASE_URL, so it needs no third-party API keys.
  # Legacy keys remain available only while the migration toggle is off.
  external_secret_names = var.enable_azure_openai ? toset([]) : toset([
    "GEMINI-API-KEY",
    "OPENAI-API-KEY",
    "SERPER-API-KEY",
    "PINECONE-API-KEY",
  ])
}
