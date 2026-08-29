# Development environment — cheapest configuration that is still production-shaped.
environment = "dev"
location    = "centralindia"

# Scale to zero between demos. The Container Apps free grant then covers the
# whole environment; the trade is a ~10-20s cold start on the first request.
# Flip to 1 for an always-warm demo (adds roughly USD 33/mo).
api_min_replicas = 0
api_max_replicas = 2
api_cpu          = 0.5
api_memory       = "1Gi"

# Cheapest SKU that runs pgvector.
postgres_sku_name   = "B_Standard_B1ms"
postgres_storage_mb = 32768

# Off until backend/app/worker.py lands.
enable_worker = false

# Turn on after Azure OpenAI quota is confirmed. This also selects pgvector and
# requires a one-time re-index because Azure embeddings are 1536-dimensional.
enable_azure_openai = false

# Hard cap on log ingestion. 0.2 GB/day caps the worst case at ~6 GB/month
# (~USD 2), while a scale-to-zero dev app realistically emits a tenth of that.
log_daily_quota_gb = 0.2

# Add operator IPs here to run psql / migrations from a laptop, e.g.
# postgres_allowed_ips = {
#   office = { start = "203.0.113.10", end = "203.0.113.10" }
# }
postgres_allowed_ips = {}

tags = {
  cost_center = "engineering"
  owner       = "platform"
}
