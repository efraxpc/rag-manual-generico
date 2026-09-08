resource "azurerm_search_service" "main" {
  name                = local.search_service_name
  resource_group_name = data.azurerm_resource_group.container_apps.name
  location            = data.azurerm_resource_group.container_apps.location
  sku                 = var.search_service_sku

  local_authentication_enabled  = false
  public_network_access_enabled = true
  network_rule_bypass_option    = "None"

  identity {
    type = "SystemAssigned"
  }

  tags = local.common_tags
}

# Las peticiones de la API usan el flujo On-Behalf-Of y llegan a Search con la
# identidad del usuario. Este grupo determina quién puede cargar y consultar.
resource "azurerm_role_assignment" "search_users_data" {
  count = var.search_user_group_object_id == null ? 0 : 1

  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = var.search_user_group_object_id
  principal_type       = "Group"
}
