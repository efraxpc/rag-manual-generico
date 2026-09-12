# Infraestructura Azure con Terraform

Configuración para autenticar Terraform con Azure y administrar dos grupos de
recursos:

- Un Resource Group y un Key Vault protegido por firewall y RBAC.
- La API desplegada en Azure Container Apps dentro del Resource Group
  preexistente `rg-fastapi-hello` y usando el ACR preexistente
  `fastapihellowkiksu`.
- Un servicio Azure AI Search con autenticación Microsoft Entra ID y acceso
  RBAC delegado para un grupo opcional de usuarios.
- Dos deployments en una cuenta Azure AI Services existente: `gpt-5-mini` para
  generar respuestas y `gpt-5` para evaluar la calidad del RAG.
- Dos identidades administradas con confianza OIDC para GitHub Actions: una
  limitada a evaluación y otra limitada al despliegue en producción.

Terraform no administra el Resource Group de Container Apps, el ACR, sus
imágenes, secretos, claves, certificados ni la cuenta Azure AI Services. Los
recursos existentes se consultan como fuentes de datos; Terraform sí administra
los dos deployments de modelos dentro de la cuenta.

Los flujos de infraestructura y seguridad están representados en:

- [`infrastructure-architecture.mmd`](infrastructure-architecture.mmd): vista
  general de los grupos de recursos, servicios, identidades y permisos RBAC.
- [`key-vault-architecture.mmd`](key-vault-architecture.mmd).
- [`azure-ai-search-entra-rbac.mmd`](azure-ai-search-entra-rbac.mmd).
- [`../../docs/github-oidc-identities.mmd`](../../docs/github-oidc-identities.mmd):
  explicación sencilla de las dos identidades usadas por GitHub Actions.

La vista general refleja la configuración Terraform del entorno `dev`. La
conexión RAG punteada requiere configurar las variables `APP_AZURE_SEARCH_*`,
preparar el índice y desplegar una imagen que incluya los endpoints vectoriales.

## Requisitos

- Terraform `>= 1.5.0` y `< 2.0.0`.
- Azure CLI.
- Una cuenta con acceso a una suscripción de Azure.
- El proveedor `Microsoft.App` registrado en la suscripción.
- El proveedor `Microsoft.Search` registrado en la suscripción.
- El proveedor `Microsoft.CognitiveServices` registrado en la suscripción.
- Permisos para administrar Resource Groups, Key Vault, Log Analytics,
  identidades, Container Apps y deployments de modelos.
- Rol `Owner` o `User Access Administrator` para crear la asignación RBAC. Si
  los accesos se administran externamente, configura
  `grant_deployer_secrets_access = false`.
- Un Resource Group y un Azure Container Registry existentes para alojar la
  aplicación y su imagen.
- La cuenta Azure AI Services `rag-manual-foundry-resource` existente en el
  Resource Group administrado, con cuota GlobalStandard para los modelos.
- El nombre exacto del repositorio de GitHub configurado en
  `github_repository`, con formato `propietario/repositorio`.

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
- Un Azure AI Search, su índice textual y, si se configura
  `search_user_group_object_id`, el rol `Search Index Data Contributor` para
  ese grupo de usuarios.
- Un deployment general `gpt-5-mini` y un deployment juez `gpt-5`, ambos con
  versión fija `2025-08-07`, SKU GlobalStandard y capacidad inicial 10.

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
  -target=azapi_data_plane_resource.text_index \
  -target=azurerm_role_assignment.search_users_data \
  -out=search.tfplan
terraform apply search.tfplan
```

Terraform crea el servicio y el índice textual. Para cargar PDF con texto, TXT y
Markdown desde la aplicación, consulta la
[guía de carga de archivos](../../docs/file-ingestion.md). El comando Python de
preparación del índice queda disponible para validar entornos existentes. Los
indexers y skillsets no están implementados.

## Deployments de Azure OpenAI

Terraform consulta la cuenta indicada por `azure_openai_account_name` y
administra dos deployments dentro de ella. No modifica la configuración de la
cuenta Azure AI Services.

| Uso | Modelo | Versión | Nombre predeterminado |
|-----|--------|---------|-----------------------|
| Generación RAG | `gpt-5-mini` | `2025-08-07` | `rag-manual-generico-dev-general` |
| Juez de calidad | `gpt-5` | `2025-08-07` | `rag-manual-generico-dev-judge` |

Ambos usan el SKU `GlobalStandard`, capacidad 10 y `NoAutoUpgrade` para que un
cambio de versión sea explícito y revisable. Los nombres y capacidades pueden
ajustarse mediante `terraform.tfvars`.

Después de aplicar un plan aprobado, consulta los valores que necesita GitHub:

```bash
terraform output -raw azure_openai_endpoint
terraform output -raw azure_openai_chat_deployment_name
terraform output -raw azure_openai_judge_deployment_name
```

Configura esos resultados respectivamente como `EVAL_AZURE_OPENAI_ENDPOINT`,
`EVAL_AZURE_OPENAI_CHAT_DEPLOYMENT` y
`EVAL_AZURE_OPENAI_JUDGE_DEPLOYMENT` en el entorno `evaluation` de GitHub.

## Identidades OIDC de GitHub Actions

Terraform crea identidades administradas separadas para los entornos protegidos
`evaluation` y `production`. Cada credencial acepta tokens solamente del
repositorio indicado por `github_repository` y del entorno correspondiente. No
se almacenan secretos de cliente.

La identidad de evaluación recibe `Search Index Data Contributor` sobre Azure
AI Search y `Cognitive Services OpenAI User` sobre la cuenta Azure AI Services.
La identidad de producción recibe `Container Registry Tasks Contributor` sobre
el ACR y `Container Apps Contributor` sobre la aplicación.

Después de aplicar un plan aprobado, obtén los Client ID:

```bash
terraform output -raw github_evaluation_identity_client_id
terraform output -raw github_production_identity_client_id
```

Configura el primer resultado como `AZURE_CLIENT_ID` en el entorno GitHub
`evaluation` y el segundo como `AZURE_CLIENT_ID` en `production`. Ambos entornos
pueden compartir `AZURE_TENANT_ID` y `AZURE_SUBSCRIPTION_ID`. Terraform no crea
los entornos ni sus variables dentro de GitHub.

## Identidades y acceso delegado a Search

`azurerm_user_assigned_identity.container_app` crea la identidad
`id-rag-manual-dev` por defecto, configurable con `container_app_identity_name`.
La Container App tiene asignada esta identidad únicamente para descargar su
imagen mediante `AcrPull`. El backend no recibe su client ID ni la usa para las
peticiones a Search.

`azurerm_role_assignment.search_users_data` concede `Search Index Data Contributor`
al grupo indicado en `search_user_group_object_id`. El rol permite a sus usuarios
cargar, actualizar, eliminar y consultar documentos mediante el flujo OBO. No
permite crear índices ni cambiar sus definiciones. Consulta los
[permisos de Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-rbac).

La identidad de Container Apps conserva únicamente `AcrPull` sobre el ACR. La
propagación de permisos del grupo en Azure puede tardar unos minutos.

Después de aplicar la configuración, consulta sus identificadores:

```bash
terraform output -raw container_app_identity_id
terraform output -raw container_app_identity_client_id
terraform output -raw container_app_identity_principal_id
```

El **client ID** selecciona la identidad al obtener un token; el **principal ID**
identifica al destinatario de los permisos RBAC. No son credenciales.
La identidad `SystemAssigned` del propio AI Search se reserva para conexiones
salientes del buscador. Tampoco representa a los usuarios de la aplicación.

Para habilitar los endpoints vectoriales también necesitas una imagen de la API
que los incluya, un índice compatible y las tres variables `APP_AZURE_SEARCH_*`
descritas en la [guía del almacén vectorial](../../docs/vector-store.md).
Las peticiones usan el login de Streamlit y el flujo On-Behalf-Of descrito en la
[guía de autenticación](../../docs/entra-auth.md). `az login` queda limitado a
Terraform y a comandos administrativos.

Terraform configura FastAPI, pero este módulo todavía no despliega la interfaz
Streamlit. En el hosting del frontend debes definir `.streamlit/secrets.toml` o
su equivalente seguro y registrar su URI pública de callback.

Terraform configura `POST /api/v1/queries/answer` en la Container App con el
endpoint de la cuenta existente y el deployment general que administra. Los
usuarios o grupos que consulten necesitan `Cognitive Services OpenAI User`
sobre el recurso y el registro de FastAPI debe poder solicitar el scope delegado
de Azure AI mediante OBO. El deployment juez pertenece al entorno de CI y no se
configura dentro de la Container App.

El workflow de release publica imágenes con el SHA del commit y actualiza la
Container App después del quality gate. Terraform ignora solamente los cambios
en `template.container.image` para no revertir una versión promovida por CI/CD;
continúa administrando la configuración, identidades, escalado e ingress.

Si configuras `entra_api_client_secret` mediante Terraform, el valor queda
almacenado en el estado aunque la variable sea sensible. Antes de usarlo en
producción, mueve el estado local a un backend remoto cifrado y con acceso
restringido, o sustituye el secreto por una credencial federada.

## Adoptar el despliegue existente

El estado de este proyecto es local y no se versiona. Un checkout nuevo no
incluye los recursos que ya se importaron o desplegaron desde otro equipo.
Recupera el estado existente o importa los recursos antes de aplicar un plan
para evitar intentar crearlos de nuevo. Esto incluye las identidades, las
asignaciones RBAC y AI Search, además del workspace, el entorno y la aplicación:

Si un `apply` termina con `already exists`, puede haber registrado otros
recursos antes de fallar. Conserva ese estado, guarda una copia y consulta
`terraform state list` desde `infrastructure/terraform/`. Importa solamente las
direcciones que falten. El comando
[`terraform import`](https://developer.hashicorp.com/terraform/cli/commands/import)
asocia un recurso existente con su dirección en el estado.

```bash
terraform import azurerm_log_analytics_workspace.container_apps \
  <log-analytics-workspace-resource-id>
terraform import azurerm_container_app_environment.main \
  <container-app-environment-resource-id>
terraform import azurerm_container_app.api \
  <container-app-resource-id>
terraform import azurerm_user_assigned_identity.container_app \
  <managed-identity-resource-id>
terraform import azurerm_role_assignment.container_app_acr_pull \
  <acr-role-assignment-resource-id>
terraform import azurerm_search_service.main \
  <search-service-resource-id>
```

El segmento del ID de la aplicación debe escribirse como `containerApps`,
respetando mayúsculas y minúsculas exigidas por AzureRM.

Después de importar, ejecuta `terraform plan` y comprueba que los recursos
existentes no aparezcan como nuevas creaciones ni como reemplazos inesperados
antes de ejecutar otro `apply`. Recupera también los valores de
`terraform.tfvars`: por ejemplo, omitir `tags` puede hacer que Terraform quite
etiquetas como `Owner` de los recursos importados.

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
infrastructure-architecture.mmd # Vista general de la infraestructura Azure
key_vault.tf               # Resource Group, Key Vault y RBAC
key-vault-architecture.mmd # Diagrama Mermaid de la arquitectura
locals.tf                  # Nombres, protección y etiquetas comunes
openai.tf                  # Deployments general y juez de Azure OpenAI
github_oidc.tf             # Identidades OIDC y permisos de GitHub Actions
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
