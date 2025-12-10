output "resource_group_name" {
  description = "The name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "acr_name" {
  description = "The name of the Azure Container Registry"
  value       = azurerm_container_registry.main.name
}

output "acr_login_server" {
  description = "The login server URL of the Azure Container Registry"
  value       = azurerm_container_registry.main.login_server
}

output "acr_admin_username" {
  description = "The admin username for the Azure Container Registry"
  value       = azurerm_container_registry.main.admin_username
  sensitive   = true
}

output "acr_admin_password" {
  description = "The admin password for the Azure Container Registry"
  value       = azurerm_container_registry.main.admin_password
  sensitive   = true
}

output "container_app_name" {
  description = "The name of the Container App"
  value       = azurerm_container_app.main.name
}

output "container_app_fqdn" {
  description = "The FQDN of the Container App"
  value       = azurerm_container_app.main.ingress[0].fqdn
}

output "container_app_url" {
  description = "The full URL of the Container App"
  value       = "https://${azurerm_container_app.main.ingress[0].fqdn}"
}

output "application_insights_instrumentation_key" {
  description = "The instrumentation key for Application Insights"
  value       = azurerm_application_insights.main.instrumentation_key
  sensitive   = true
}

output "application_insights_connection_string" {
  description = "The connection string for Application Insights"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "log_analytics_workspace_id" {
  description = "The ID of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.id
}

output "container_app_environment_name" {
  description = "The name of the Container Apps Environment"
  value       = azurerm_container_app_environment.main.name
}

# Summary output for easy reference
output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    resource_group       = azurerm_resource_group.main.name
    location             = azurerm_resource_group.main.location
    acr_login_server     = azurerm_container_registry.main.login_server
    container_app_url    = "https://${azurerm_container_app.main.ingress[0].fqdn}"
    app_insights_enabled = true
  }
}
