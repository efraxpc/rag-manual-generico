# GitHub Actions obtiene tokens temporales mediante OIDC. Cada entorno usa una
# identidad distinta para que evaluación no pueda desplegar y producción no
# pueda consultar los datos usados por el quality gate.
resource "azurerm_user_assigned_identity" "github_evaluation" {
  name                = "id-${local.resource_prefix}-github-eval"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_federated_identity_credential" "github_evaluation" {
  name                      = "github-evaluation"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_evaluation.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:environment:evaluation"
}

resource "azurerm_role_assignment" "github_evaluation_search_data" {
  scope                            = azurerm_search_service.main.id
  role_definition_name             = "Search Index Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.github_evaluation.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "github_evaluation_openai_user" {
  scope                            = data.azurerm_cognitive_account.openai.id
  role_definition_name             = "Cognitive Services OpenAI User"
  principal_id                     = azurerm_user_assigned_identity.github_evaluation.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_user_assigned_identity" "github_production" {
  name                = "id-${local.resource_prefix}-github-prod"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_federated_identity_credential" "github_production" {
  name                      = "github-production"
  user_assigned_identity_id = azurerm_user_assigned_identity.github_production.id
  audience                  = ["api://AzureADTokenExchange"]
  issuer                    = "https://token.actions.githubusercontent.com"
  subject                   = "repo:${var.github_repository}:environment:production"
}

resource "azurerm_role_assignment" "github_production_acr_build" {
  scope                            = data.azurerm_container_registry.main.id
  role_definition_name             = "Container Registry Tasks Contributor"
  principal_id                     = azurerm_user_assigned_identity.github_production.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "github_production_container_app" {
  scope                            = azurerm_container_app.api.id
  role_definition_name             = "Container Apps Contributor"
  principal_id                     = azurerm_user_assigned_identity.github_production.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
