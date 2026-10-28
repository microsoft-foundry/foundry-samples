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

## Grant the project managed identity read access so evaluations can query agent traces
## Log Analytics Reader + Privileged Monitoring Data Reader (the latter is required to read GenAI content)
locals {
  application_insights_reader_role_definition_ids = toset([
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/73c42c96-874c-492b-b04d-ab87d138a893",
    "/subscriptions/${data.azurerm_client_config.current.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/dbc9c667-e97f-4491-aee6-90b9cf960190"
  ])
}

resource "azurerm_role_assignment" "application_insights_reader" {
  for_each                         = local.application_insights_reader_role_definition_ids
  scope                            = azurerm_application_insights.app_insights.id
  role_definition_id               = each.value
  principal_id                     = azapi_resource.ai_project.identity[0].principal_id
  skip_service_principal_aad_check = true
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
      isSharedToAll = false
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
