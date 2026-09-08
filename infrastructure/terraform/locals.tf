locals {
  entra_auth_values = [
    var.entra_tenant_id,
    var.entra_api_client_id,
    var.entra_api_client_secret,
    var.entra_frontend_client_id,
  ]
  entra_auth_enabled = nonsensitive(alltrue([
    for value in local.entra_auth_values : value != null
  ]))

  normalized_project_name = trim(
    replace(
      replace(lower(var.project_name), "/[^0-9a-z-]/", "-"),
      "/-+/",
      "-"
    ),
    "-"
  )
  normalized_resource_prefix = "${local.normalized_project_name}-${var.environment}"
  resource_prefix            = substr(local.normalized_resource_prefix, 0, min(80, length(local.normalized_resource_prefix)))
  resource_group_name        = "rg-${local.resource_prefix}"

  # Key Vault exige un nombre globalmente único de 3 a 24 caracteres.
  # El entorno evita colisiones entre despliegues y el hash de la suscripción
  # mantiene el nombre estable sin agregar otro proveedor.
  key_vault_hash               = substr(md5(data.azurerm_client_config.current.subscription_id), 0, 8)
  key_vault_project_max_length = 11 - length(var.environment)
  key_vault_project_prefix     = trim(substr(local.normalized_project_name, 0, min(local.key_vault_project_max_length, length(local.normalized_project_name))), "-")
  key_vault_name               = "kv-${local.key_vault_project_prefix}-${var.environment}-${local.key_vault_hash}"

  # Azure AI Search exige un nombre globalmente único de 2 a 60 caracteres.
  # Se conserva el hash al final incluso cuando el nombre del proyecto es largo.
  search_service_hash               = substr(md5(data.azurerm_client_config.current.subscription_id), 0, 8)
  search_service_project_max_length = 60 - length("srch--${var.environment}-${local.search_service_hash}")
  search_service_project_prefix     = trim(substr(local.normalized_project_name, 0, min(local.search_service_project_max_length, length(local.normalized_project_name))), "-")
  search_service_default_name       = "srch-${local.search_service_project_prefix}-${var.environment}-${local.search_service_hash}"
  search_service_name               = var.search_service_name != null ? var.search_service_name : local.search_service_default_name

  protected_environment      = contains(["staging", "prod"], var.environment)
  soft_delete_retention_days = local.protected_environment ? 90 : 7
  purge_protection_enabled   = local.protected_environment

  common_tags = merge(
    {
      Environment = var.environment
      ManagedBy   = "Terraform"
      Project     = var.project_name
    },
    var.tags
  )
}
