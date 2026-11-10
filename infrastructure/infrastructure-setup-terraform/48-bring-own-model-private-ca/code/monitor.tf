# Log Analytics + Application Insights. APIM logs into App Insights so the
# TLS/backend behaviour of the gateway leg is observable and can be
# cross-referenced against the data-proxy-side failure (mirrors the perf-bed
# methodology: prove where the latency/error actually lives).

resource "azurerm_log_analytics_workspace" "law" {
  name                = local.law_name
  location            = var.location
  resource_group_name = local.rg_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_application_insights" "appi" {
  name                = local.appi_name
  location            = var.location
  resource_group_name = local.rg_name
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
  tags                = local.common_tags
}
