resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_key_vault" "main" {
  name                = local.key_vault_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = var.key_vault_sku_name

  rbac_authorization_enabled    = true
  public_network_access_enabled = true
  soft_delete_retention_days    = local.soft_delete_retention_days
  purge_protection_enabled      = local.purge_protection_enabled

  network_acls {
    bypass         = "AzureServices"
    default_action = "Deny"
    ip_rules       = var.allowed_ip_cidrs
  }

  tags = local.common_tags
}

resource "azurerm_role_assignment" "deployer_secrets_officer" {
  count = var.grant_deployer_secrets_access ? 1 : 0

  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}
