// ─────────────────────────────────────────────────────────────────────────────
// Container Apps environment (Consumption plan)
// ─────────────────────────────────────────────────────────────────────────────
// Consumption bills per vCPU-second and GiB-second with a monthly free grant
// (180k vCPU-s + 360k GiB-s). With min_replicas = 0 a dev environment sits
// inside that grant and costs effectively nothing between demos.
resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

// Azure Files mounts. ACA authenticates to Files with the account key — this is
// the one place a key is still required, and it never leaves the environment.
resource "azurerm_container_app_environment_storage" "shares" {
  for_each = azurerm_storage_share.main

  name                         = each.key
  container_app_environment_id = azurerm_container_app_environment.main.id
  account_name                 = azurerm_storage_account.main.name
  share_name                   = each.value.name
  access_key                   = azurerm_storage_account.main.primary_access_key
  access_mode                  = "ReadWrite"
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared container configuration
// ─────────────────────────────────────────────────────────────────────────────
locals {
  // Secrets are referenced versionlessly, so rotating a value in Key Vault
  // takes effect on the next revision without a Terraform run.
  app_secrets = merge(
    {
      "database-url" = azurerm_key_vault_secret.database_url.versionless_id
      "secret-key"   = azurerm_key_vault_secret.jwt_secret.versionless_id
    },
    {
      for name in local.external_secret_names :
      lower(name) => azurerm_key_vault_secret.external[name].versionless_id
    },
  )

  app_env = {
    // Runtime
    PORT  = "8000"
    DEBUG = "false"

    // Providers — unchanged from today (Gemini + Pinecone), so the first
    // Azure deploy is a lift, not a rewrite. Migration is report §6.
    LLM_PROVIDER         = "gemini"
    EMBEDDING_PROVIDER   = "gemini"
    VECTOR_STORE_BACKEND = "pinecone"
    GRAPH_STORE_BACKEND  = "json_kv"

    // Paths backed by the Azure Files mounts.
    LIGHTRAG_DATA_DIR = "/data/lightrag"
    UPLOAD_DIR        = "/data/uploads"

    // Rebuildable caches stay on the container's own disk: losing them costs
    // a few API calls, not data.
    VLM_CACHE_DIR          = "/tmp/vlm_cache"
    IMAGE_SEARCH_CACHE_DIR = "/tmp/image_search_cache"

    // Azure resources the app can address by managed identity.
    AZURE_CLIENT_ID                = azurerm_user_assigned_identity.app.client_id
    AZURE_STORAGE_ACCOUNT_NAME     = azurerm_storage_account.main.name
    AZURE_BLOB_DOCUMENTS_CONTAINER = "documents"

    // Observability
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string

    // CORS — see report §4.4: the app hardcodes allow_origins=["*"] today and
    // must be changed to read this before the environment is exposed.
    CORS_ALLOWED_ORIGINS = join(",", local.cors_origins)
  }

  openai_env = var.enable_azure_openai ? {
    LLM_PROVIDER                  = "azure_openai"
    EMBEDDING_PROVIDER            = "azure_openai"
    VECTOR_STORE_BACKEND          = "pgvector"
    AZURE_OPENAI_ENDPOINT         = azurerm_cognitive_account.openai[0].endpoint
    AZURE_OPENAI_CHAT_DEPLOYMENT  = var.azure_openai_chat_model.name
    AZURE_OPENAI_EMBED_DEPLOYMENT = var.azure_openai_embedding_model.name
  } : {}
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────
resource "azurerm_container_app" "api" {
  name                         = "ca-${local.name}-api"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = local.app_secrets
    content {
      name                = secret.key
      key_vault_secret_id = secret.value
      identity            = azurerm_user_assigned_identity.app.id
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.api_min_replicas
    max_replicas = var.api_max_replicas

    container {
      name   = "api"
      image  = var.container_image
      cpu    = var.api_cpu
      memory = var.api_memory

      dynamic "env" {
        for_each = merge(local.app_env, local.openai_env)
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.app_secrets
        content {
          // database-url -> DATABASE_URL
          name        = upper(replace(env.key, "-", "_"))
          secret_name = env.key
        }
      }

      // Probes hit "/", not "/health": the health endpoint calls Gemini and the
      // database on every request, so probing it would bill an LLM call every
      // few seconds. See report §4.5 — the fix is a cheap /health/live route.
      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/"
        initial_delay           = 20
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/"
        interval_seconds        = 15
        failure_count_threshold = 3
      }

      volume_mounts {
        name = "lightrag-data"
        path = "/data/lightrag"
      }

      volume_mounts {
        name = "uploads"
        path = "/data/uploads"
      }
    }

    dynamic "volume" {
      for_each = azurerm_container_app_environment_storage.shares
      content {
        name         = volume.key
        storage_type = "AzureFile"
        storage_name = volume.value.name
      }
    }
  }

  lifecycle {
    // After the first apply the deploy-backend workflow owns the image tag.
    // Terraform must not drag it back to the bootstrap quickstart image.
    ignore_changes = [
      template[0].container[0].image,
    ]
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Indexing worker — same image, different command. Opt in with enable_worker
// once backend/app/worker.py exists.
// ─────────────────────────────────────────────────────────────────────────────
resource "azurerm_container_app" "worker" {
  count = var.enable_worker ? 1 : 0

  name                         = "ca-${local.name}-worker"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  dynamic "secret" {
    for_each = local.app_secrets
    content {
      name                = secret.key
      key_vault_secret_id = secret.value
      identity            = azurerm_user_assigned_identity.app.id
    }
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name    = "worker"
      image   = var.container_image
      cpu     = 0.5
      memory  = "1Gi"
      command = ["arq"]
      args    = ["app.worker.WorkerSettings"]

      dynamic "env" {
        for_each = merge(local.app_env, local.openai_env)
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.app_secrets
        content {
          name        = upper(replace(env.key, "-", "_"))
          secret_name = env.key
        }
      }

      volume_mounts {
        name = "lightrag-data"
        path = "/data/lightrag"
      }

      volume_mounts {
        name = "uploads"
        path = "/data/uploads"
      }
    }

    dynamic "volume" {
      for_each = azurerm_container_app_environment_storage.shares
      content {
        name         = volume.key
        storage_type = "AzureFile"
        storage_name = volume.value.name
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]
  }
}
