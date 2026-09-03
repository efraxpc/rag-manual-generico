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
