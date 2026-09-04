# Infraestructura Azure con Terraform

Configuración para autenticar Terraform con Azure y administrar dos grupos de
recursos:

- Un Resource Group y un Key Vault protegido por firewall y RBAC.
- La API desplegada en Azure Container Apps dentro del Resource Group
  preexistente `rg-fastapi-hello` y usando el ACR preexistente
  `fastapihellowkiksu`.
- Un servicio Azure AI Search con autenticación Microsoft Entra ID y acceso
  RBAC para la identidad administrada de la API.

Terraform no administra el Resource Group de Container Apps, el ACR, sus
imágenes, secretos, claves ni certificados. Ambos recursos se consultan como
fuentes de datos para evitar asumir propiedad sobre el AKS y los demás recursos
que comparten ese grupo.

Los flujos de infraestructura y seguridad están representados en:

- [`key-vault-architecture.mmd`](key-vault-architecture.mmd).
- [`azure-ai-search-entra-rbac.mmd`](azure-ai-search-entra-rbac.mmd).

## Requisitos

- Terraform `>= 1.5.0` y `< 2.0.0`.
- Azure CLI.
- Una cuenta con acceso a una suscripción de Azure.
- El proveedor `Microsoft.App` registrado en la suscripción.
- El proveedor `Microsoft.Search` registrado en la suscripción.
- Permisos para administrar Resource Groups, Key Vault, Log Analytics,
  identidades y Container Apps.
- Rol `Owner` o `User Access Administrator` para crear la asignación RBAC. Si
  los accesos se administran externamente, configura
  `grant_deployer_secrets_access = false`.
- Un Resource Group y un Azure Container Registry existentes para alojar la
  aplicación y su imagen.

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

Edita `terraform.tfvars`, selecciona una etiqueta inmutable existente en el ACR
y agrega las IP públicas autorizadas para Key Vault. Para un solo equipo,
utiliza su IP pública con una máscara `/32`:

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
- Un workspace de Log Analytics.
- Un Azure Container Apps Environment con perfil Consumption.
- Una identidad administrada asignada por el usuario y su rol `AcrPull`.
- Una Container App con HTTPS público, una sola revisión activa y escalado
  configurable, incluido scale-to-zero.
- Un Azure AI Search y el rol `Search Index Data Contributor` para que la API
  pueda consultar y cargar documentos sin API keys.

La imagen debe existir antes de ejecutar `terraform apply`. Puede construirse y
publicarse mediante ACR Tasks:

```bash
az acr build \
  --registry fastapihellowkiksu \
  --image rag-manual-api:<tag> \
  ../..
```

Actualiza `container_image_tag` con el mismo `<tag>` antes del plan.

Para desplegar únicamente Azure AI Search sin aplicar los recursos pendientes
de Key Vault:

```bash
terraform plan \
  -target=azurerm_search_service.main \
  -target=azurerm_role_assignment.container_app_search_data \
  -out=search.tfplan
terraform apply search.tfplan
```

El recurso crea solamente el servicio. Los índices, indexers, skillsets y la
carga de documentos deben versionarse e implementarse posteriormente mediante
el SDK o la API REST de Azure AI Search.

## Adoptar el despliegue existente

Los recursos creados inicialmente mediante Azure CLI ya fueron importados al
estado local de este workspace. Si se parte de otro estado, importa el
workspace, el entorno y la aplicación antes de ejecutar un plan:

```bash
terraform import azurerm_log_analytics_workspace.container_apps \
  <log-analytics-workspace-resource-id>
terraform import azurerm_container_app_environment.main \
  <container-app-environment-resource-id>
terraform import azurerm_container_app.api \
  <container-app-resource-id>
```

El segmento del ID de la aplicación debe escribirse como `containerApps`,
respetando mayúsculas y minúsculas exigidas por AzureRM.

Consulta el resultado con:

```bash
terraform output
az keyvault show --name "$(terraform output -raw key_vault_name)"
curl "$(terraform output -raw container_app_url)/api/v1/health"
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
azure-ai-search-entra-rbac.mmd # Diagrama de Entra ID y RBAC de AI Search
container_app.tf           # Log Analytics, identidad, RBAC y Container Apps
data.tf                    # Identidad y suscripción activas
key_vault.tf               # Resource Group, Key Vault y RBAC
key-vault-architecture.mmd # Diagrama Mermaid de la arquitectura
locals.tf                  # Nombres, protección y etiquetas comunes
outputs.tf                 # Contexto de Azure y datos del Key Vault
providers.tf               # Configuración del proveedor AzureRM
search.tf                  # Azure AI Search y acceso de la aplicación
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
