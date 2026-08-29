# One Standard LRS account carries three jobs:
#   1. Blob containers  — document originals and rebuildable caches (S3 replacement)
#   2. File shares      — mounted into Container Apps so state that today lives on
#                         the container's disk survives a revision (see report §4.2)
#   3. Nothing else. Premium/GRS/geo-replication are launch-time concerns.
resource "azurerm_storage_account" "main" {
  name                     = local.storage_account_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  access_tier              = "Hot"

  https_traffic_only_enabled = true
  min_tls_version            = "TLS1_2"

  # Azure Files mounts in Container Apps authenticate with an account key,
  # so shared-key access has to stay on. Blob access still goes through the
  # managed identity via the role assignment below.
  shared_access_key_enabled       = true
  allow_nested_items_to_be_public = false

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = local.tags
}

resource "azurerm_role_assignment" "blob_contributor" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# ── Blob containers ──────────────────────────────────────────────────────────
locals {
  blob_containers = {
    documents      = "User uploads and textbook originals (the AWS S3 bucket's replacement)"
    vlm-cache      = "Gemini Vision page transcriptions, keyed by content hash"
    image-cache    = "Serper diagram images that passed AI verification"
    eval-artifacts = "RAGAS / DeepEval run outputs produced by CI"
  }
}

resource "azurerm_storage_container" "main" {
  for_each = local.blob_containers

  name                  = each.key
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

# ── File shares mounted into Container Apps ──────────────────────────────────
# `lightrag-data` is the important one: the graph KV store writes JSON to local
# disk, which a Container Apps revision throws away. Mounting it is the
# no-code-change fix; moving it into Postgres JSONB is the real fix (report §6).
locals {
  file_shares = {
    lightrag-data = 5 # GiB
    uploads       = 20
  }
}

resource "azurerm_storage_share" "main" {
  for_each = local.file_shares

  name               = each.key
  storage_account_id = azurerm_storage_account.main.id
  quota              = each.value
}
