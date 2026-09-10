# Carga y almacenamiento de fragmentos de texto

Streamlit envía un archivo a FastAPI, que extrae su texto, lo divide y guarda
cada fragmento en Azure AI Search. No genera embeddings, no realiza OCR ni
conserva el archivo original. El servicio existente de Azure AI Search sirve
para este flujo, con un índice textual separado del vectorial.

## Preparar el entorno y el índice

Instala las dependencias con `pip install -e ".[dev]"` y configura en `.env`:

```dotenv
APP_AZURE_SEARCH_ENDPOINT="https://<servicio>.search.windows.net"
APP_AZURE_SEARCH_TEXT_INDEX_NAME="rag-text-chunks"
```

No hacen falta dimensiones ni un modelo de embeddings. Puedes mantener las
variables vectoriales existentes usando un nombre de índice distinto. Configurar
un índice sin endpoint, un endpoint sin índices, o un índice vectorial sin
dimensiones es un error de configuración.

El servicio de Azure AI Search debe existir. Con una identidad que tenga
`Search Service Contributor` sobre el servicio, prepara el índice:

```bash
az login
python -m app.commands.prepare_text_index
```

Este comando **crea un índice en Azure si no existe**. Si ya existe, comprueba
los campos necesarios y sus capacidades sin modificarlo. Ante incompatibilidad
termina con código 1; configura otro nombre para crear un índice nuevo. No borra
ni reemplaza índices o datos. No se ejecuta automáticamente al arrancar la API.

El índice contiene `id` (clave), `chunk_id`, `document_id` (filtrable), `content`
(buscable), `source` y `page` (entero opcional). Todos son recuperables y no hay
campo vectorial. Su definición está en `app.commands.prepare_text_index`.

Para **cargar documentos**, cada usuario necesita `Search Index Data Contributor`
sobre el servicio o el índice. FastAPI intercambia el token de la interfaz por un
token de Search mediante On-Behalf-Of. La identidad administrada de Container Apps
no tiene permisos de datos en Search y la API no la usa como alternativa. Consulta
la [guía de autenticación delegada](entra-auth.md).

Para una puesta en marcha posterior en Container Apps, incorpora
`APP_AZURE_SEARCH_ENDPOINT` y `APP_AZURE_SEARCH_TEXT_INDEX_NAME` a las variables
del contenedor y publica una imagen con esta implementación. Terraform también
inyecta la configuración de Entra si completas sus cuatro variables. Aplicar la
infraestructura y publicar la imagen siguen siendo pasos separados.

## Uso desde la interfaz o la API

Configura primero Entra ID según la guía de autenticación. Después ejecuta
`./scripts/run_local.sh`, inicia sesión, selecciona un archivo y pulsa **Procesar y
guardar**. La interfaz muestra el número de fragmentos guardados y las páginas
omitidas. Las reevaluaciones de Streamlit no vuelven a enviar el archivo.
Después de una carga correcta, el formulario recupera fragmentos del documento
por búsqueda textual y genera una respuesta citada con Azure OpenAI. Configura el
deployment según la [guía de autenticación](entra-auth.md).

También puedes utilizar el endpoint directamente:

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H 'Authorization: Bearer <token-para-la-api>' \
  -F 'file=@manual.pdf'
```

Respuesta `200` de ejemplo (el hash y el número dependen del archivo):

```json
{
  "document_id": "746b241a97027bb7b9820c9a66275501abc04ef1b1e4da0cab4c9a11cfaa2677",
  "source": "manual.pdf",
  "indexed_chunks": 12,
  "warnings": ["Página 2 omitida: no contiene texto extraíble; si es una imagen, necesita OCR."]
}
```

Con el `document_id` de esa respuesta también puedes consultar directamente:

```bash
curl -X POST http://localhost:8000/api/v1/queries/answer \
  -H 'Authorization: Bearer <token-para-la-api>' \
  -H 'Content-Type: application/json' \
  -d '{"question":"¿Qué mantenimiento requiere?","document_id":"<hash>"}'
```

La respuesta incluye `answer` y los fragmentos de `context` usados. Si no se
recupera contexto, devuelve una respuesta segura y no llama al modelo generador.

Se admite un archivo por petición de hasta **10 MiB**:

- PDF con texto extraíble, sin contraseña ni cifrado. Cada página se procesa
  por separado; páginas sin texto se omiten con una advertencia. No se interpreta
  la estructura de tablas o columnas y los escaneados necesitan OCR.
- TXT y Markdown en UTF-8, con o sin BOM. Markdown se conserva como texto.

Se normalizan saltos de línea y se crean ventanas de 1.000 caracteres con 200
de solapamiento, eliminando espacios al principio y al final de cada fragmento.
No se generan fragmentos vacíos ni una última ventana que solo repita el
solapamiento. `page` empieza en 1 para PDF y es `null` para TXT y Markdown.

El identificador del documento es el SHA-256 de nombre sin directorios, separador
nulo y bytes del archivo. Los fragmentos usan IDs basados en página y posición.
Reenviar el mismo nombre y contenido reutiliza las claves. Cambiar contenido o
nombre crea otro documento y conserva el anterior. No hay borrado de versiones.
Esta estabilidad presupone la misma extracción y configuración de chunking;
un cambio futuro de algoritmo requiere gestionar la reindexación y los datos antiguos.

## Errores y reintentos

Los errores de aplicación usan `{"error":{"code":"...","message":"...","details":null}}`:

| HTTP | Situación |
|------|-----------|
| 413 | Archivo superior a 10 MiB. |
| 415 | Extensión no admitida. |
| 422 | Nombre inválido, texto vacío o no UTF-8, PDF dañado, cifrado o sin texto. Un archivo ausente usa la validación estándar de FastAPI. |
| 401 | Token ausente, caducado, mal firmado o destinado a otra API. |
| 403 | Falta consentimiento delegado o el usuario no tiene el rol necesario en Search o Azure OpenAI. |
| 502 | Azure rechazó fragmentos, devolvió una respuesta incompatible o el modelo generador falló. |
| 503 | Almacén textual sin configurar, índice inexistente o fallo de conexión con Azure. |

La indexación usa lotes de hasta 1.000 documentos y un presupuesto conservador
de 15 MB serializados para respetar el máximo de 16 MB de Azure. No es una
transacción: si un lote falla, se detiene el procesamiento y algunos fragmentos
pueden haber quedado guardados. Reintenta con el mismo archivo; la interfaz
solo muestra éxito si se confirman todos los fragmentos.

Las pruebas usan almacenes y clientes simulados, junto a PDF pequeños generados
en memoria. No requieren recursos ni credenciales de Azure.

## Referencias

- [Carga de archivos en FastAPI](https://fastapi.tiangolo.com/tutorial/request-files/).
- [Extracción con pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).
- [Carga por lotes en Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-what-is-data-import).
- [Roles de Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-security-rbac).
