# Terraform para Azure Key Vault

Configuración base para autenticar Terraform con Azure y aprovisionar un Key
Vault por entorno. Crea un Resource Group, un Key Vault protegido por firewall
y una asignación RBAC para el principal que ejecuta Terraform. No administra
secretos, claves ni certificados.

El flujo completo está representado en
[`key-vault-architecture.mmd`](key-vault-architecture.mmd).

## Requisitos

- Terraform `>= 1.5.0` y `< 2.0.0`.
- Azure CLI.
- Una cuenta con acceso a una suscripción de Azure.
- Permisos para crear Resource Groups y Key Vaults.
- Rol `Owner` o `User Access Administrator` para crear la asignación RBAC. Si
  los accesos se administran externamente, configura
  `grant_deployer_secrets_access = false`.

## 1. Autenticarse en Azure

```bash
az login
az account list --output table
az account set --subscription "<nombre-o-id-de-la-suscripcion>"
az account show
```

Terraform usa por defecto la suscripción activa de Azure CLI. No guardes
contraseñas, tokens ni secretos en archivos `.tf` o `.tfvars`.

## 2. Configurar el entorno

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
```

Edita `terraform.tfvars` y agrega las IP públicas autorizadas. Para un solo
equipo, utiliza su IP pública con una máscara `/32`:

```hcl
allowed_ip_cidrs = [
  "198.51.100.25/32",
]
```

Los rangos del ejemplo son reservados para documentación; sustitúyelos por
rangos reales. Si `allowed_ip_cidrs` queda vacío, Terraform puede administrar
el recurso mediante Azure Resource Manager, pero el acceso al plano de datos
del vault permanece bloqueado desde Internet.

## 3. Inicializar y desplegar

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out main.tfplan
terraform apply main.tfplan
```

El despliegue crea:

- Un Resource Group etiquetado para el proyecto y entorno.
- Un Key Vault `standard` con autorización RBAC.
- Un firewall con denegación predeterminada y los CIDR declarados.
- El rol `Key Vault Secrets Officer` para el principal que ejecutó Terraform,
  salvo que se desactive mediante una variable.

Consulta el resultado con:

```bash
terraform output
az keyvault show --name "$(terraform output -raw key_vault_name)"
```

## Protección contra borrado

La protección depende del entorno:

| Entorno | Retención soft delete | Purge protection |
|---------|-----------------------|------------------|
| `dev`, `test` | 7 días | Desactivada |
| `staging`, `prod` | 90 días | Activada |

Purge protection no puede desactivarse una vez habilitada. Un vault protegido
que se elimine permanecerá recuperable y no podrá purgarse ni reutilizar su
nombre hasta que finalice el periodo de retención.

## Estructura

```text
backend.tf                 # Estado local inicial
data.tf                    # Identidad y suscripción activas
key_vault.tf               # Resource Group, Key Vault y RBAC
key-vault-architecture.mmd # Diagrama Mermaid de la arquitectura
locals.tf                  # Nombres, protección y etiquetas comunes
outputs.tf                 # Contexto de Azure y datos del Key Vault
providers.tf               # Configuración del proveedor AzureRM
terraform.tfvars.example   # Ejemplo de valores por entorno
variables.tf               # Entradas del proyecto
versions.tf                # Versiones de Terraform y AzureRM
```

## Siguientes pasos

- Agrega las identidades administradas de las aplicaciones con el rol mínimo
  que necesiten sobre el Key Vault.
- Crea secretos mediante un proceso seguro fuera de Terraform para evitar que
  sus valores queden almacenados en el estado.
- Antes de usar CI/CD o colaborar con otras personas, migra el estado a un
  backend remoto `azurerm` con bloqueo y acceso restringido.
- Para eliminar el acceso público por completo, agrega una VNet, Private
  Endpoint y zona DNS privada.
