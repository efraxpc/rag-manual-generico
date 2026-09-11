# Esta consulta valida la autenticación y no crea recursos en Azure.
data "azurerm_client_config" "current" {}

# El Resource Group y el ACR ya existían antes de este despliegue. Se consultan
# en lugar de administrarlos para no asumir propiedad sobre otros recursos que
# comparten el grupo, como el clúster AKS existente.
data "azurerm_resource_group" "container_apps" {
  name = var.container_apps_resource_group_name
}

data "azurerm_container_registry" "main" {
  name                = var.container_registry_name
  resource_group_name = data.azurerm_resource_group.container_apps.name
}

# La cuenta existe previamente; Terraform administra solamente sus deployments.
data "azurerm_cognitive_account" "openai" {
  name                = var.azure_openai_account_name
  resource_group_name = azurerm_resource_group.main.name
}
