# RBAC-authorised vault: access is granted by Azure role assignments rather
# than legacy access policies, so the same OIDC principal that runs Terraform
# can manage secrets and nothing else needs a policy edit.
resource "azurerm_key_vault" "main" {
  name                       = local.key_vault_name
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  purge_protection_enabled   = false # dev tier: keep `destroy` reversible-free
  soft_delete_retention_days = 7
  tags                       = local.tags
}

# The Terraform runner needs to write the placeholder secrets below.
resource "azurerm_role_assignment" "kv_terraform_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# The container apps only ever read.
resource "azurerm_role_assignment" "kv_app_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Azure RBAC is eventually consistent; without this the first apply on a fresh
# subscription fails writing secrets a few seconds after granting the role.
resource "time_sleep" "kv_rbac_propagation" {
  depends_on      = [azurerm_role_assignment.kv_terraform_officer]
  create_duration = "45s"
}

# ─────────────────────────────────────────────────────────────────────────────
# Secrets
# ─────────────────────────────────────────────────────────────────────────────
resource "random_password" "postgres_admin" {
  length           = 32
  special          = true
  override_special = "!#$%*()-_=+[]{}<>:?"
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "azurerm_key_vault_secret" "postgres_password" {
  name         = "POSTGRES-ADMIN-PASSWORD"
  value        = random_password.postgres_admin.result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.kv_rbac_propagation]
}

resource "azurerm_key_vault_secret" "database_url" {
  name = "DATABASE-URL"
  value = format(
    "postgresql://%s:%s@%s:5432/%s?sslmode=require",
    var.postgres_admin_username,
    urlencode(random_password.postgres_admin.result),
    azurerm_postgresql_flexible_server.main.fqdn,
    local.postgres_database_name,
  )
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.kv_rbac_propagation]
}

resource "azurerm_key_vault_secret" "jwt_secret" {
  name         = "SECRET-KEY"
  value        = random_password.jwt_secret.result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.kv_rbac_propagation]

  # Rotating this invalidates every issued JWT — make it a deliberate act,
  # never a side effect of a Terraform run.
  lifecycle {
    ignore_changes = [value]
  }
}

# Third-party credentials: Terraform creates the slot, a human (or a scoped
# workflow) fills it. `ignore_changes` means a later apply never reverts the
# real value back to the placeholder.
resource "azurerm_key_vault_secret" "external" {
  for_each = toset(local.external_secret_names)

  name         = each.value
  value        = "REPLACE_ME"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.kv_rbac_propagation]

  lifecycle {
    ignore_changes = [value]
  }
}
