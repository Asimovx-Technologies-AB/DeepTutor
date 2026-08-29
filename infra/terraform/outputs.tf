output "resource_group_name" {
  description = "The single resource group holding every application resource."
  value       = azurerm_resource_group.main.name
}

output "api_url" {
  description = "Public HTTPS URL of the backend. Feed this to VITE_API_BASE_URL as <url>/api."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "api_container_app_name" {
  description = "Container app name — used by the deploy-backend workflow."
  value       = azurerm_container_app.api.name
}

output "worker_container_app_name" {
  description = "Worker container app name, or null when enable_worker is false."
  value       = var.enable_worker ? azurerm_container_app.worker[0].name : null
}

output "frontend_url" {
  description = "Public URL of the SPA."
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "static_web_app_name" {
  description = "Static Web App name — the deploy-frontend workflow reads its deployment token by name."
  value       = azurerm_static_web_app.frontend.name
}

output "container_registry_login_server" {
  description = "ACR login server, e.g. crdeeptutordevab12cd.azurecr.io"
  value       = azurerm_container_registry.main.login_server
}

output "container_registry_name" {
  description = "ACR name — used by `az acr build` / `az acr login` in CI."
  value       = azurerm_container_registry.main.name
}

output "key_vault_name" {
  description = "Key Vault holding DATABASE-URL, SECRET-KEY and the third-party API key slots."
  value       = azurerm_key_vault.main.name
}

output "postgres_fqdn" {
  description = "PostgreSQL Flexible Server hostname."
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_database_name" {
  description = "Application database on the server."
  value       = azurerm_postgresql_flexible_server_database.main.name
}

output "storage_account_name" {
  description = "Blob + Files account backing documents, caches and the ACA volume mounts."
  value       = azurerm_storage_account.main.name
}

output "application_insights_connection_string" {
  description = "Wired into the container apps automatically; exposed here for local debugging."
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "managed_identity_client_id" {
  description = "Client ID of the platform identity (ACR pull, Key Vault read, Blob write)."
  value       = azurerm_user_assigned_identity.app.client_id
}

output "secrets_to_populate" {
  description = "Key Vault secrets Terraform created empty. Fill them before the first real deploy."
  value       = local.external_secret_names
}
