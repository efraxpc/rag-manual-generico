output "azure_connection" {
  description = "Contexto de Azure usado por el proveedor. Los identificadores no son credenciales."
  value = {
    object_id       = data.azurerm_client_config.current.object_id
    subscription_id = data.azurerm_client_config.current.subscription_id
    tenant_id       = data.azurerm_client_config.current.tenant_id
  }
}

output "resource_defaults" {
  description = "Valores reutilizables al agregar recursos."
  value = {
    location = var.location
    prefix   = local.resource_prefix
    tags     = local.common_tags
  }
}

output "resource_group_name" {
  description = "Nombre del Resource Group administrado por Terraform."
  value       = azurerm_resource_group.main.name
}

output "key_vault_id" {
  description = "ID del Azure Key Vault."
  value       = azurerm_key_vault.main.id
}

output "key_vault_name" {
  description = "Nombre global del Azure Key Vault."
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "URI del plano de datos del Azure Key Vault."
  value       = azurerm_key_vault.main.vault_uri
}

output "container_registry_login_server" {
  description = "Servidor del Azure Container Registry que aloja la imagen."
  value       = data.azurerm_container_registry.main.login_server
}

output "container_app_environment_id" {
  description = "ID del Azure Container Apps Environment."
  value       = azurerm_container_app_environment.main.id
}

output "container_app_fqdn" {
  description = "Dominio público de la API."
  value       = azurerm_container_app.api.ingress[0].fqdn
}

output "container_app_url" {
  description = "URL HTTPS pública de la API."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "container_app_identity_id" {
  description = "ID de la identidad administrada usada por la aplicación."
  value       = azurerm_user_assigned_identity.container_app.id
}

output "search_service_id" {
  description = "ID de Azure AI Search."
  value       = azurerm_search_service.main.id
}

output "search_service_name" {
  description = "Nombre de Azure AI Search."
  value       = azurerm_search_service.main.name
}

output "search_service_endpoint" {
  description = "Endpoint HTTPS de Azure AI Search."
  value       = azurerm_search_service.main.endpoint
}
