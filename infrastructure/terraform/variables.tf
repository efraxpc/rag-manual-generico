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

variable "tags" {
  description = "Etiquetas adicionales para futuros recursos."
  type        = map(string)
  default     = {}
}
