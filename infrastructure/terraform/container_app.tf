resource "azurerm_log_analytics_workspace" "container_apps" {
  name                = var.log_analytics_workspace_name
  location            = data.azurerm_resource_group.container_apps.location
  resource_group_name = data.azurerm_resource_group.container_apps.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.common_tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = var.container_app_environment_name
  location                   = data.azurerm_resource_group.container_apps.location
  resource_group_name        = data.azurerm_resource_group.container_apps.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.container_apps.id
  logs_destination           = "log-analytics"
  public_network_access      = "Enabled"
  tags                       = local.common_tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

# Una identidad asignada por el usuario permite crear el permiso de lectura del
# ACR antes que la aplicación, evitando credenciales y dependencias circulares.
resource "azurerm_user_assigned_identity" "container_app" {
  name                = var.container_app_identity_name
  location            = data.azurerm_resource_group.container_apps.location
  resource_group_name = data.azurerm_resource_group.container_apps.name
  tags                = local.common_tags
}

resource "azurerm_role_assignment" "container_app_acr_pull" {
  scope                            = data.azurerm_container_registry.main.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.container_app.principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_container_app" "api" {
  name                         = var.container_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = data.azurerm_resource_group.container_apps.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.common_tags

  dynamic "secret" {
    for_each = local.entra_auth_enabled ? [1] : []
    content {
      name  = "entra-api-client-secret"
      value = local.entra_api_client_secret
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.container_app.id]
  }

  registry {
    server   = data.azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.container_app.id
  }

  ingress {
    external_enabled           = true
    allow_insecure_connections = false
    target_port                = var.container_app_target_port
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas                = var.container_app_min_replicas
    max_replicas                = var.container_app_max_replicas
    cooldown_period_in_seconds  = 300
    polling_interval_in_seconds = 30

    container {
      name   = var.container_app_name
      image  = "${data.azurerm_container_registry.main.login_server}/${var.container_image_repository}:${var.container_image_tag}"
      cpu    = var.container_app_cpu
      memory = var.container_app_memory

      env {
        name  = "APP_ENVIRONMENT"
        value = var.container_app_environment
      }

      env {
        name  = "APP_DEBUG"
        value = "false"
      }

      env {
        name  = "APP_AZURE_SEARCH_ENDPOINT"
        value = azurerm_search_service.main.endpoint
      }

      env {
        name  = "APP_AZURE_SEARCH_TEXT_INDEX_NAME"
        value = azapi_data_plane_resource.text_index.name
      }

      env {
        name  = "APP_AZURE_OPENAI_ENDPOINT"
        value = data.azurerm_cognitive_account.openai.endpoint
      }

      env {
        name  = "APP_AZURE_OPENAI_CHAT_DEPLOYMENT"
        value = azurerm_cognitive_deployment.general.name
      }

      dynamic "env" {
        for_each = local.entra_auth_enabled ? [1] : []
        content {
          name  = "APP_ENTRA_TENANT_ID"
          value = var.entra_tenant_id
        }
      }

      dynamic "env" {
        for_each = local.entra_auth_enabled ? [1] : []
        content {
          name  = "APP_ENTRA_API_CLIENT_ID"
          value = var.entra_api_client_id
        }
      }

      dynamic "env" {
        for_each = local.entra_auth_enabled ? [1] : []
        content {
          name        = "APP_ENTRA_API_CLIENT_SECRET"
          secret_name = "entra-api-client-secret"
        }
      }

      dynamic "env" {
        for_each = local.entra_auth_enabled ? [1] : []
        content {
          name  = "APP_ENTRA_FRONTEND_CLIENT_ID"
          value = var.entra_frontend_client_id
        }
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.container_app_acr_pull,
  ]

  lifecycle {
    # Terraform crea la aplicación, pero CI/CD promociona imágenes inmutables con
    # `az containerapp update`; un plan de infraestructura no debe revertir releases.
    ignore_changes = [template[0].container[0].image]

    precondition {
      condition = (
        (alltrue([for value in local.entra_auth_values : value == null]) &&
          !var.create_entra_api_client_secret &&
        nonsensitive(var.entra_api_client_secret == null)) ||
        local.entra_auth_enabled
      )
      error_message = "Configura los tres IDs de Entra y proporciona entra_api_client_secret o activa create_entra_api_client_secret."
    }

    precondition {
      condition = (
        !local.entra_auth_enabled ||
        var.entra_api_client_id != var.entra_frontend_client_id
      )
      error_message = "Los registros de aplicación de FastAPI y Streamlit deben ser distintos."
    }
  }
}
