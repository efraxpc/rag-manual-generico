provider "azuread" {
  tenant_id = var.entra_tenant_id
}

data "azuread_application" "api" {
  count     = var.create_entra_api_client_secret ? 1 : 0
  client_id = var.entra_api_client_id

  lifecycle {
    precondition {
      condition     = var.entra_api_client_id != null && var.entra_tenant_id != null
      error_message = "Para crear la credencial, configura entra_api_client_id y entra_tenant_id."
    }
  }
}

# Añade una credencial propia sin reemplazar las credenciales de otros clientes.
resource "azuread_application_password" "container_app" {
  count          = var.create_entra_api_client_secret ? 1 : 0
  application_id = data.azuread_application.api[0].id
  display_name   = "terraform-container-app-obo"

  lifecycle {
    precondition {
      condition     = nonsensitive(var.entra_api_client_secret == null)
      error_message = "Usa una credencial proporcionada o una administrada por Terraform, no ambas."
    }
  }
}
