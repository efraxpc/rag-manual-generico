# Autenticación delegada con Microsoft Entra ID

La interfaz inicia sesión con Microsoft y obtiene un token destinado a FastAPI.
FastAPI valida ese token y usa el flujo OAuth 2.0 On-Behalf-Of (OBO) para obtener
tokens de Azure AI Search y Azure OpenAI que representan al mismo usuario. Cada
servicio aplica los roles RBAC del usuario o de sus grupos.

Consulta también los diagramas preparados para impresión:

- [Configuración de Entra ID, Terraform y RBAC](entra-auth-configuration.mmd).
- [Flujo OIDC y On-Behalf-Of por petición](entra-auth-runtime.mmd).

```text
Usuario -> Streamlit -> token access_as_user -> FastAPI
                                             -> intercambio OBO
                                             -> token de Search / Azure AI
                                             -> recuperar contexto y generar
```

No hay acceso anónimo a los endpoints de documentos o consultas. `/api/v1/health`
permanece público. La identidad administrada de Container Apps solo conserva
`AcrPull`; no tiene rol de datos en Search y el código no recurre a ella si OBO
o RBAC fallan.

## 1. Registro de aplicación para FastAPI

En Microsoft Entra ID, crea un registro de aplicación de un solo tenant para la
API. Anota su **Application (client) ID** y el **Directory (tenant) ID**.

En **Expose an API**:

1. Establece el Application ID URI como `api://<client-id-api>`.
2. Añade el scope delegado `access_as_user`, habilitado para usuarios y admins.

En **API permissions**, añade los permisos delegados `user_impersonation` de
Azure AI Search y Azure AI Services, y concede consentimiento de administrador
para el tenant. OBO requiere ese consentimiento en el registro de la API.

Crea una credencial para la aplicación de la API. El código admite actualmente
un client secret. Guárdalo fuera de Git; en producción debe llegar mediante un
almacén de secretos y no como un valor versionado.

Los registros de aplicación de Entra no se crean en este repositorio. Terraform
recibe sus IDs y el secreto para configurar FastAPI. Si pasas el secreto con
`TF_VAR_entra_api_client_secret`, recuerda que Terraform lo guarda en el estado:
usa un backend remoto cifrado y restringido antes de un despliegue de producción.

## 2. Registro de aplicación para Streamlit

Crea otro registro de aplicación de un solo tenant. Debe ser distinto del de la
API. Añade una plataforma **Web** con estas URI de redirección:

- Local: `http://localhost:8501/oauth2callback`.
- Producción: `https://<dominio-streamlit>/oauth2callback`.

Crea su client secret. En **API permissions**, añade el permiso delegado
`access_as_user` expuesto por la API. Puedes preautorizar este client ID desde
**Expose an API > Authorized client applications** para evitar solicitudes de
consentimiento individuales.

## 3. Permisos de usuarios en Azure AI Search

Asigna `Search Index Data Contributor` a un grupo de Entra que contenga los
usuarios autorizados. El rol permite cargar, consultar y eliminar documentos,
pero no cambiar la definición del índice.

Asigna también `Cognitive Services OpenAI User` al mismo grupo —o a otro grupo
autorizado— sobre el recurso Azure OpenAI usado para generar respuestas.

Terraform acepta el Object ID del grupo:

```hcl
search_user_group_object_id = "<object-id-del-grupo>"
```

Con `null`, Terraform no asigna permisos a usuarios. Los roles pueden tardar
unos minutos en propagarse. Para solo consultar, una evolución futura puede
separar lectores con `Search Index Data Reader`; la carga actual requiere el rol
de contribuidor.

## 4. Configuración local

Copia el ejemplo de Streamlit y completa ambos secretos:

```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

En `.streamlit/secrets.toml`, sustituye tenant, client IDs, secretos y conserva
el scope `api://<client-id-api>/access_as_user`. El archivo real está ignorado
por Git. Genera `cookie_secret` con un valor aleatorio, por ejemplo:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Completa `.env` para FastAPI:

```dotenv
APP_AZURE_SEARCH_ENDPOINT="https://<servicio>.search.windows.net"
APP_AZURE_SEARCH_TEXT_INDEX_NAME="rag-text-chunks"
APP_AZURE_OPENAI_ENDPOINT="https://<recurso>.openai.azure.com"
APP_AZURE_OPENAI_CHAT_DEPLOYMENT="<despliegue-generador>"
APP_ENTRA_TENANT_ID="<tenant-id>"
APP_ENTRA_API_CLIENT_ID="<client-id-api>"
APP_ENTRA_API_CLIENT_SECRET="<secret-api>"
APP_ENTRA_FRONTEND_CLIENT_ID="<client-id-streamlit>"
```

Instala dependencias y arranca ambos procesos:

```bash
pip install -e ".[dev]"
./scripts/run_local.sh
```

Abre `http://localhost:8501`, inicia sesión, carga un archivo y formula una
pregunta. `az login` no se usa para las peticiones de la aplicación. Sigue siendo
necesario para Terraform y los comandos administrativos o de evaluación.
Si se accede mediante otro alias local, como `127.0.0.1`, la interfaz navega
primero a `localhost` antes de iniciar OIDC para que el callback conserve las
cookies de sesión y abra directamente la vista principal.

El Terraform actual despliega FastAPI en Container Apps, pero no despliega
Streamlit. Configura los secretos OIDC y la URI de callback en el hosting que
elijas para la interfaz.

## Validaciones y errores

FastAPI acepta únicamente tokens v2 firmados por el tenant configurado, con
audiencia igual al client ID de la API, scope `access_as_user` y `azp` igual al
client ID de Streamlit. Un token ausente, caducado o inválido devuelve `401`; un
scope o cliente incorrecto devuelve `403`. Un fallo de consentimiento OBO o de
RBAC devuelve `403`, y la indisponibilidad de Entra devuelve `503`.

Los tokens y secretos no se incluyen en respuestas ni logs. Los clientes de
Search son por petición y se cierran al terminar, evitando mezclar credenciales
entre sesiones. La generación de respuestas abre también un cliente Azure
OpenAI por petición con la misma identidad OBO. Streamlit fija la URL de FastAPI
mediante `APP_API_BASE_URL` y no permite al usuario cambiar el destino al que
envía el bearer token.

## Referencias

- [On-Behalf-Of en Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow).
- [Autenticación de Microsoft en Streamlit](https://docs.streamlit.io/develop/tutorials/authentication/microsoft).
- [Roles de Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-rbac).
