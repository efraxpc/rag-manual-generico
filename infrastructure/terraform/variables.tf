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
  description = "Nombre de la identidad administrada usada para descargar imágenes del ACR."
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

variable "tags" {
  description = "Etiquetas adicionales para futuros recursos."
  type        = map(string)
  default     = {}
}
