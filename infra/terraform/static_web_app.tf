# Free tier: global CDN, TLS, custom domains, 100 GB bandwidth/month — USD 0.
# It replaces both Netlify and Vercel, which the repo currently deploys to in
# parallel (frontend/netlify.toml and the two vercel.json files).
#
# Note the Free tier has no "linked backend", so the SPA calls the Container
# App URL directly with VITE_API_BASE_URL. That is why CORS on the API has to
# be narrowed to this hostname (report §4.4).
resource "azurerm_static_web_app" "frontend" {
  name                = "stapp-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.static_web_app_location
  sku_tier            = "Free"
  sku_size            = "Free"
  tags                = local.tags
}
