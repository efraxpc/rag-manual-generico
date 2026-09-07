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

Para **cargar documentos**, la identidad de la API necesita
`Search Index Data Contributor`. Terraform ya declara ese rol para la identidad
de Container Apps. En local, los permisos deben asignarse al usuario utilizado
por `az login`; los permisos de la identidad de Azure no se transfieren al usuario.
`DefaultAzureCredential` autentica ambas operaciones sin claves API.

Para una puesta en marcha posterior en Container Apps, incorpora
`APP_AZURE_SEARCH_ENDPOINT` y `APP_AZURE_SEARCH_TEXT_INDEX_NAME` a las variables
del contenedor y publica una imagen con esta implementación. Mantén
`APP_AZURE_MANAGED_IDENTITY_CLIENT_ID`, ya configurada por Terraform. Este cambio
no despliega la imagen, no aplica Terraform y no crea el índice por sí solo.

## Uso desde la interfaz o la API

Ejecuta `./scripts/run_local.sh`, selecciona un archivo y pulsa **Procesar y
guardar**. La interfaz muestra el número de fragmentos guardados y las páginas
omitidas. Las reevaluaciones de Streamlit no vuelven a enviar el archivo.
El formulario de preguntas todavía prepara la consulta sin generar respuestas.

También puedes utilizar el endpoint directamente:

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
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
| 502 | Azure rechazó fragmentos o no devolvió su confirmación; `details.failed_chunks` identifica los fallidos del lote. |
| 503 | Almacén textual sin configurar, índice inexistente, falta de permisos o fallo de conexión con Azure. |

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
