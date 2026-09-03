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
    }
  }

  depends_on = [azurerm_role_assignment.container_app_acr_pull]
}
