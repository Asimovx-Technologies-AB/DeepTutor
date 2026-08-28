# Burstable B1ms: 1 vCore / 2 GiB, ~USD 12/mo + storage. It is the cheapest SKU
# that still runs pgvector, which is what lets one server be the relational
# database, the vector index, AND the knowledge-graph store — replacing three
# separate paid services (Neon + Pinecone + local disk).
resource "azurerm_postgresql_flexible_server" "main" {
  name                = "psql-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  version                = var.postgres_version
  sku_name               = var.postgres_sku_name
  storage_mb             = var.postgres_storage_mb
  auto_grow_enabled      = true

  administrator_login    = var.postgres_admin_username
  administrator_password = random_password.postgres_admin.result

  backup_retention_days        = var.postgres_backup_retention_days
  geo_redundant_backup_enabled = false

  # Dev tier: public endpoint guarded by firewall rules + TLS. A VNet-injected
  # server with a private endpoint is the production hardening step, and costs
  # roughly the price of the server again.
  public_network_access_enabled = true

  zone = "1"

  tags = local.tags

  lifecycle {
    # Storage cannot be shrunk, and auto_grow will legitimately move it.
    ignore_changes = [storage_mb, zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = local.postgres_database_name
  server_id = azurerm_postgresql_flexible_server.main.id
  collation = "en_US.utf8"
  charset   = "utf8"

  lifecycle {
    prevent_destroy = true
  }
}

# Extensions must be allow-listed on the server before `CREATE EXTENSION` works.
#   vector    — pgvector, the vector index
#   pg_trgm   — trigram similarity, backs fuzzy/sparse retrieval
#   uuid-ossp — id generation for the ORM
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR,PG_TRGM,UUID-OSSP"
}

# Container Apps egress with the environment's outbound IPs, which are not
# stable on the Consumption plan; this rule is the documented way to let them in.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Operator / CI access for migrations and psql, opt-in per IP.
resource "azurerm_postgresql_flexible_server_firewall_rule" "operators" {
  for_each = var.postgres_allowed_ips

  name             = each.key
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = each.value.start
  end_ip_address   = each.value.end
}
