########## Create Azure Monitor resources for agent tracing
##########
## Deploys Application Insights and an Azure Monitor Private Link Scope (AMPLS) so agents
## running in the VNet can export OpenTelemetry traces to Application Insights over the
## private network instead of having the spans dropped.

## Create the Log Analytics workspace that backs Application Insights
##
resource "azurerm_log_analytics_workspace" "loganalytics" {
  name                = "loganalytics-tracing-${random_string.unique.result}"
  location            = var.location
  resource_group_name = local.rg_name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

## Create the workspace-based Application Insights. Public ingestion is disabled; traces
## are ingested privately through the Azure Monitor Private Link Scope below.
##
resource "azurerm_application_insights" "app_insights" {
  name                       = "appinsights-tracing-${random_string.unique.result}"
  location                   = var.location
  resource_group_name        = local.rg_name
  workspace_id               = azurerm_log_analytics_workspace.loganalytics.id
  application_type           = "web"
  internet_ingestion_enabled = false
  internet_query_enabled     = true
}

## Create the Azure Monitor Private Link Scope (private ingestion, open query)
##
resource "azurerm_monitor_private_link_scope" "ampls" {
  name                  = "ampls-tracing-${random_string.unique.result}"
  resource_group_name   = local.rg_name
  ingestion_access_mode = "PrivateOnly"
  query_access_mode     = "Open"
}

## Scope Application Insights and the Log Analytics workspace into the AMPLS
##
resource "azurerm_monitor_private_link_scoped_service" "ampls_app_insights" {
  name                = "appinsights-scoped"
  resource_group_name = local.rg_name
  scope_name          = azurerm_monitor_private_link_scope.ampls.name
  linked_resource_id  = azurerm_application_insights.app_insights.id
}

resource "azurerm_monitor_private_link_scoped_service" "ampls_loganalytics" {
  name                = "loganalytics-scoped"
  resource_group_name = local.rg_name
  scope_name          = azurerm_monitor_private_link_scope.ampls.name
  linked_resource_id  = azurerm_log_analytics_workspace.loganalytics.id
}

## Create the Azure Monitor Private DNS Zones. The blob zone is intentionally omitted: it is
## already created (or supplied through existing_dns_zones_resource_group) for the storage account.
##
resource "azurerm_private_dns_zone" "plz_monitor" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.monitor.azure.com"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_oms" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.oms.opinsights.azure.com"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_ods" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.ods.opinsights.azure.com"
  resource_group_name = local.rg_name
}

resource "azurerm_private_dns_zone" "plz_agentsvc" {
  count               = local.create_dns_zones ? 1 : 0
  name                = "privatelink.agentsvc.azure-automation.net"
  resource_group_name = local.rg_name
}

## Create Private DNS Zone Links to link the Azure Monitor zones to the virtual network
##
resource "azurerm_private_dns_zone_virtual_network_link" "plz_monitor_link" {
  count                 = local.create_dns_zones ? 1 : 0
  name                  = "monitor-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_monitor[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_oms_link" {
  count                 = local.create_dns_zones ? 1 : 0
  name                  = "oms-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_oms[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false

  depends_on = [azurerm_private_dns_zone_virtual_network_link.plz_monitor_link]
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_ods_link" {
  count                 = local.create_dns_zones ? 1 : 0
  name                  = "ods-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_ods[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false

  depends_on = [azurerm_private_dns_zone_virtual_network_link.plz_oms_link]
}

resource "azurerm_private_dns_zone_virtual_network_link" "plz_agentsvc_link" {
  count                 = local.create_dns_zones ? 1 : 0
  name                  = "agentsvc-${random_string.unique.result}-link"
  resource_group_name   = local.rg_name
  private_dns_zone_name = azurerm_private_dns_zone.plz_agentsvc[0].name
  virtual_network_id    = local.vnet_id
  registration_enabled  = false

  depends_on = [azurerm_private_dns_zone_virtual_network_link.plz_ods_link]
}

## Create the Private Endpoint for the AMPLS (group "azuremonitor")
##
resource "azurerm_private_endpoint" "pe_ampls" {
  depends_on = [
    azurerm_monitor_private_link_scoped_service.ampls_app_insights,
    azurerm_monitor_private_link_scoped_service.ampls_loganalytics,
    azurerm_private_dns_zone_virtual_network_link.plz_agentsvc_link,
    azurerm_private_endpoint.pe_ai_foundry
  ]

  name                = "ampls-tracing-${random_string.unique.result}-private-endpoint"
  location            = var.location
  resource_group_name = local.rg_name
  subnet_id           = local.subnet_pe_id

  private_service_connection {
    name                           = "ampls-tracing-private-link-service-connection"
    private_connection_resource_id = azurerm_monitor_private_link_scope.ampls.id
    subresource_names              = ["azuremonitor"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name = "ampls-tracing-dns-config"
    private_dns_zone_ids = [
      local.dns_zone_monitor_id,
      local.dns_zone_oms_id,
      local.dns_zone_ods_id,
      local.dns_zone_agentsvc_id,
      local.dns_zone_storage_blob_id
    ]
  }
}

## Create the AI Foundry project connection to Application Insights so the agent exports
## its OpenTelemetry traces here
##
resource "azapi_resource" "conn_app_insights" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name                      = azurerm_application_insights.app_insights.name
  parent_id                 = azapi_resource.ai_project.id
  schema_validation_enabled = false

  depends_on = [
    azapi_resource.ai_project,
    azurerm_private_endpoint.pe_ampls
  ]

  body = {
    name = azurerm_application_insights.app_insights.name
    properties = {
      category = "AppInsights"
      target   = azurerm_application_insights.app_insights.id
      authType = "ApiKey"
      credentials = {
        key = azurerm_application_insights.app_insights.connection_string
      }
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_application_insights.app_insights.id
        location   = var.location
      }
    }
  }
}

## Grant the project managed identity read access on Application Insights so evaluation
## can read the agent traces exported by hosted agents, including GenAI prompt/response
## content, which requires the Privileged Monitoring Data Reader role.
##
resource "azurerm_role_assignment" "log_analytics_reader_ai_foundry_project" {
  depends_on = [
    time_sleep.wait_project_identities
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}${local.rg_name}loganalyticsreader")
  scope                = azurerm_application_insights.app_insights.id
  role_definition_name = "Log Analytics Reader"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
}

resource "azurerm_role_assignment" "privileged_monitoring_data_reader_ai_foundry_project" {
  depends_on = [
    time_sleep.wait_project_identities
  ]
  name                 = uuidv5("dns", "${azapi_resource.ai_project.name}${azapi_resource.ai_project.output.identity.principalId}${local.rg_name}privmonitoringdatareader")
  scope                = azurerm_application_insights.app_insights.id
  role_definition_name = "Privileged Monitoring Data Reader"
  principal_id         = azapi_resource.ai_project.output.identity.principalId
}
