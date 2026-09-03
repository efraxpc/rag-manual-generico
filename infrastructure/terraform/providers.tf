provider "azurerm" {
  features {}

  # Con valores null, AzureRM usa la suscripción y el tenant activos en Azure CLI.
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}
