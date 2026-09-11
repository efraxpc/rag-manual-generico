variable "subscription_id" {
  description = "ID de la suscripción de Azure. Si es null, se usa la suscripción activa de Azure CLI."
  type        = string
  default     = null
  nullable    = true
}

variable "tenant_id" {
  description = "ID del tenant de Microsoft Entra. Si es null, se obtiene de la sesión de Azure CLI."
  type        = string
  default     = null
  nullable    = true
}

variable "project_name" {
  description = "Nombre corto del proyecto, usado como base para nombres y etiquetas."
  type        = string
  default     = "rag-manual-generico"

  validation {
    condition = (
      length(trimspace(var.project_name)) > 0 &&
      length(var.project_name) <= 64 &&
      can(regex("[0-9A-Za-z]", var.project_name))
    )
    error_message = "project_name debe contener entre 1 y 64 caracteres e incluir al menos una letra o número."
  }
}

variable "environment" {
  description = "Entorno al que pertenecen los recursos."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "staging", "prod"], var.environment)
    error_message = "environment debe ser dev, test, staging o prod."
  }
}

variable "location" {
  description = "Región predeterminada para futuros recursos de Azure."
  type        = string
  default     = "brazilsouth"
}

variable "key_vault_sku_name" {
  description = "SKU de Azure Key Vault. Usa premium solo si necesitas claves protegidas por HSM."
  type        = string
  default     = "standard"

  validation {
    condition     = contains(["standard", "premium"], var.key_vault_sku_name)
    error_message = "key_vault_sku_name debe ser standard o premium."
  }
}

variable "allowed_ip_cidrs" {
  description = "Rangos IPv4 con acceso al plano de datos del Key Vault. Una lista vacía mantiene el acceso bloqueado."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.allowed_ip_cidrs : can(cidrnetmask(cidr))])
    error_message = "Cada elemento de allowed_ip_cidrs debe ser un CIDR IPv4 válido."
  }
}

variable "grant_deployer_secrets_access" {
  description = "Concede Key Vault Secrets Officer al principal que ejecuta Terraform."
  type        = bool
  default     = true
}

variable "container_apps_resource_group_name" {
  description = "Resource Group existente que contiene el ACR y los recursos de Container Apps."
  type        = string
  default     = "rg-fastapi-hello"
}

variable "container_registry_name" {
  description = "Nombre del Azure Container Registry existente."
  type        = string
  default     = "fastapihellowkiksu"
}

variable "log_analytics_workspace_name" {
  description = "Nombre del workspace de Log Analytics usado por Container Apps."
  type        = string
  default     = "workspace-rgfastapihellovmC5"
}

variable "container_app_environment_name" {
  description = "Nombre del Azure Container Apps Environment."
  type        = string
  default     = "cae-rag-manual-dev"
}

variable "container_app_identity_name" {
  description = "Nombre de la identidad administrada usada por Container Apps para descargar imágenes del ACR."
  type        = string
  default     = "id-rag-manual-dev"
}

variable "container_app_name" {
  description = "Nombre de la Azure Container App."
  type        = string
  default     = "rag-manual-api"
}

variable "container_image_repository" {
  description = "Repositorio de la imagen dentro del ACR."
  type        = string
  default     = "rag-manual-api"
}

variable "container_image_tag" {
  description = "Etiqueta inmutable de la imagen que debe desplegarse."
  type        = string
  default     = "ce4ae6b"
}

variable "container_app_environment" {
  description = "Valor de APP_ENVIRONMENT dentro del contenedor."
  type        = string
  default     = "production"
}

variable "container_app_target_port" {
  description = "Puerto HTTP expuesto por el contenedor."
  type        = number
  default     = 8000

  validation {
    condition     = var.container_app_target_port >= 1 && var.container_app_target_port <= 65535
    error_message = "container_app_target_port debe estar entre 1 y 65535."
  }
}

variable "container_app_cpu" {
  description = "Cantidad de vCPU asignada a cada réplica."
  type        = number
  default     = 0.5
}

variable "container_app_memory" {
  description = "Memoria asignada a cada réplica."
  type        = string
  default     = "1Gi"
}

variable "container_app_min_replicas" {
  description = "Número mínimo de réplicas; cero habilita scale-to-zero."
  type        = number
  default     = 0
}

variable "container_app_max_replicas" {
  description = "Número máximo de réplicas."
  type        = number
  default     = 3

  validation {
    condition     = var.container_app_max_replicas >= var.container_app_min_replicas
    error_message = "container_app_max_replicas debe ser mayor o igual que container_app_min_replicas."
  }
}

variable "azure_openai_account_name" {
  description = "Nombre de la cuenta Azure AI Services existente donde Terraform administra los deployments OpenAI."
  type        = string
  default     = "rag-manual-foundry-resource"

  validation {
    condition = (
      length(var.azure_openai_account_name) >= 2 &&
      length(var.azure_openai_account_name) <= 64 &&
      can(regex("^[0-9A-Za-z](?:[0-9A-Za-z-]*[0-9A-Za-z])?$", var.azure_openai_account_name))
    )
    error_message = "azure_openai_account_name debe tener entre 2 y 64 caracteres alfanuméricos o guiones, sin guiones al inicio o al final."
  }
}

variable "azure_openai_chat_deployment" {
  description = "Nombre opcional del deployment general; null genera un nombre estable con el proyecto y entorno."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.azure_openai_chat_deployment == null ||
      length(trimspace(var.azure_openai_chat_deployment)) > 0
    )
    error_message = "azure_openai_chat_deployment no puede estar vacío."
  }
}

variable "azure_openai_judge_deployment" {
  description = "Nombre opcional del deployment juez; null genera un nombre estable con el proyecto y entorno."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.azure_openai_judge_deployment == null ||
      length(trimspace(var.azure_openai_judge_deployment)) > 0
    )
    error_message = "azure_openai_judge_deployment no puede estar vacío."
  }
}

variable "azure_openai_chat_capacity" {
  description = "Capacidad GlobalStandard del deployment general gpt-5-mini."
  type        = number
  default     = 10

  validation {
    condition = (
      var.azure_openai_chat_capacity >= 1 &&
      floor(var.azure_openai_chat_capacity) == var.azure_openai_chat_capacity
    )
    error_message = "azure_openai_chat_capacity debe ser un entero positivo."
  }
}

variable "azure_openai_judge_capacity" {
  description = "Capacidad GlobalStandard del deployment juez gpt-5."
  type        = number
  default     = 10

  validation {
    condition = (
      var.azure_openai_judge_capacity >= 1 &&
      floor(var.azure_openai_judge_capacity) == var.azure_openai_judge_capacity
    )
    error_message = "azure_openai_judge_capacity debe ser un entero positivo."
  }
}

variable "search_service_name" {
  description = "Nombre global de Azure AI Search. Si es null, se genera uno estable con la suscripción."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.search_service_name == null ||
      (
        length(var.search_service_name) >= 2 &&
        length(var.search_service_name) <= 60 &&
        can(regex("^[a-z0-9]+(?:-[a-z0-9]+)*$", var.search_service_name))
      )
    )
    error_message = "search_service_name debe tener entre 2 y 60 caracteres, usar minúsculas, números o guiones simples, y no comenzar ni terminar con guion."
  }
}

variable "search_service_sku" {
  description = "SKU de Azure AI Search."
  type        = string
  default     = "free"

  validation {
    condition = contains(
      ["free", "basic", "standard", "standard2", "standard3", "storage_optimized_l1", "storage_optimized_l2"],
      var.search_service_sku
    )
    error_message = "search_service_sku debe ser un SKU compatible con Azure AI Search."
  }
}

variable "search_user_group_object_id" {
  description = "Object ID opcional del grupo de Entra autorizado a cargar y consultar documentos en Azure AI Search mediante acceso delegado."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.search_user_group_object_id == null ||
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$", var.search_user_group_object_id))
    )
    error_message = "search_user_group_object_id debe ser un UUID válido o null."
  }
}

variable "entra_tenant_id" {
  description = "Tenant ID de Microsoft Entra usado por Streamlit y FastAPI."
  type        = string
  default     = null
  nullable    = true
}

variable "entra_api_client_id" {
  description = "Client ID del registro de aplicación de FastAPI."
  type        = string
  default     = null
  nullable    = true
}

variable "entra_api_client_secret" {
  description = "Client secret del registro de FastAPI para el intercambio On-Behalf-Of. Pásalo mediante TF_VAR_entra_api_client_secret."
  type        = string
  default     = null
  nullable    = true
  sensitive   = true
}

variable "entra_frontend_client_id" {
  description = "Client ID del registro de aplicación de Streamlit autorizado para llamar a FastAPI."
  type        = string
  default     = null
  nullable    = true
}

variable "tags" {
  description = "Etiquetas adicionales para futuros recursos."
  type        = map(string)
  default     = {}
}
