## Create workspace-based Application Insights for project tracing
resource "azurerm_log_analytics_workspace" "log_analytics" {
  name                = "${local.account_name}-law"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "app_insights" {
  name                = "${local.account_name}-appi"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  workspace_id        = azurerm_log_analytics_workspace.log_analytics.id
  application_type    = "web"
}

## Connect Application Insights to the Foundry project (key-based)
resource "azapi_resource" "application_insights_connection" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview"
  name                      = "appinsights"
  parent_id                 = azapi_resource.ai_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      category      = "AppInsights"
      target        = azurerm_application_insights.app_insights.id
      authType      = "ApiKey"
      isSharedToAll = true
      credentials = {
        key = azurerm_application_insights.app_insights.connection_string
      }
      metadata = {
        ApiType                             = "Azure"
        ResourceId                          = azurerm_application_insights.app_insights.id
        ApplicationInsightsConnectionString = azurerm_application_insights.app_insights.connection_string
      }
    }
  }
}
