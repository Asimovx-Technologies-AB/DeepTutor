# Optional. S0 is pay-per-token with no idle charge, so the account itself is
# free to leave provisioned — but switching the embedding provider changes the
# vector dimension and forces a full re-index, which is why this is off by
# default and gated behind report §6.4.
resource "azurerm_cognitive_account" "openai" {
  count = var.enable_azure_openai ? 1 : 0

  name                  = "oai-${local.name}"
  resource_group_name   = azurerm_resource_group.main.name
  location              = var.azure_openai_location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-${local.name}-${local.unique_suffix}"

  # Key-free access: the app authenticates with the same managed identity it
  # uses for ACR, Key Vault and Blob Storage.
  local_auth_enabled = false

  tags = local.tags
}

resource "azurerm_role_assignment" "openai_user" {
  count = var.enable_azure_openai ? 1 : 0

  scope                = azurerm_cognitive_account.openai[0].id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_cognitive_deployment" "chat" {
  count = var.enable_azure_openai ? 1 : 0

  name                 = var.azure_openai_chat_model.name
  cognitive_account_id = azurerm_cognitive_account.openai[0].id

  model {
    format  = "OpenAI"
    name    = var.azure_openai_chat_model.name
    version = var.azure_openai_chat_model.version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.azure_openai_chat_model.capacity
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  count = var.enable_azure_openai ? 1 : 0

  name                 = var.azure_openai_embedding_model.name
  cognitive_account_id = azurerm_cognitive_account.openai[0].id

  model {
    format  = "OpenAI"
    name    = var.azure_openai_embedding_model.name
    version = var.azure_openai_embedding_model.version
  }

  sku {
    name     = "Standard"
    capacity = var.azure_openai_embedding_model.capacity
  }
}
