# Esta consulta valida la autenticación y no crea recursos en Azure.
data "azurerm_client_config" "current" {}
