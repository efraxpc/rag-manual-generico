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

# La identidad de la API carga y consulta chunks en este servicio. La identidad
# SystemAssigned de AI Search se reserva para conexiones salientes del buscador.
resource "azurerm_role_assignment" "container_app_search_data" {
  scope                            = azurerm_search_service.main.id
  role_definition_name             = "Search Index Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.container_app.principal_id
  skip_service_principal_aad_check = true
}
