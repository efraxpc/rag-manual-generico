# Almacenamiento vectorial con el patrón Adapter

La implementación conecta los servicios de ingesta y consulta con Azure AI
Search mediante el contrato `VectorStore`. El diagrama está en
[`architecture/rag-adapter.mmd`](architecture/rag-adapter.mmd).

## Responsabilidades

- `app/rag/contracts.py`: contrato `VectorStore`, independiente del proveedor.
- `app/rag/models.py`: chunks con embeddings, consultas y resultados.
- `app/services/ingestion.py`: valida IDs duplicados y solicita la indexación.
- `app/services/query.py`: solicita la recuperación de chunks.
- `app/integrations/azure_search.py`: adapta documentos y consultas al SDK,
  normaliza resultados y convierte fallos del proveedor en errores controlados.
- `app/core/resources.py`: construye el cliente y la credencial una vez durante
  el arranque y los cierra al apagar la aplicación.
- `app/api/dependencies.py`: inyecta el contrato en los servicios con FastAPI.

Los endpoints son funciones síncronas: FastAPI ejecuta las operaciones del SDK
en su pool de hilos. Los servicios no importan clases de Azure y las pruebas
pueden sustituir el almacén por una implementación en memoria.

Este cambio cubre almacenamiento y recuperación de embeddings precalculados.
La extracción de PDF, el chunking, la generación de embeddings y las respuestas
de un LLM siguen pendientes. Streamlit conserva su interfaz de preparación de
consultas; todavía no invoca estos endpoints vectoriales.

## Configuración y autenticación

Instala las dependencias con `pip install -e ".[dev]"`. Para habilitar el
almacén, configura las tres propiedades en `.env`:

```dotenv
APP_AZURE_SEARCH_ENDPOINT="https://<servicio>.search.windows.net"
APP_AZURE_SEARCH_INDEX_NAME="rag-chunks"
APP_AZURE_SEARCH_VECTOR_DIMENSIONS=3
```

Las tres se configuran conjuntamente. Si no se configura ninguna, la API y
`/api/v1/health` siguen funcionando; las operaciones vectoriales devuelven
`503` con código `vector_store_not_configured`.

Se utiliza `DefaultAzureCredential`, sin claves API. En desarrollo puede usar
la sesión de `az login`. El principal local necesita permisos sobre los datos
del índice; el rol asignado a la identidad de Container Apps no se transfiere
automáticamente al usuario local.

En Container Apps configura también
`APP_AZURE_MANAGED_IDENTITY_CLIENT_ID` con el **client ID** de la identidad
asignada a la aplicación. El rol `Search Index Data Contributor` ya está
declarado para esa identidad en Terraform. Estas variables de aplicación aún
deben incorporarse a la configuración del despliegue cuando se habilite el RAG.

Esta autenticación identifica a la API ante Azure AI Search. No implementa
autenticación de usuarios en los endpoints HTTP; ese control de acceso sigue
pendiente antes de exponer las nuevas operaciones a usuarios externos.

## Índice requerido

El índice debe existir antes de ejecutar las operaciones. Se incluye una
[definición de ejemplo](architecture/azure-search-index.example.json) compatible
con el adaptador. Usa un índice nuevo para probarla; no sobrescribas uno que
contenga datos de otra aplicación.

El ejemplo y las peticiones de esta guía usan **tres dimensiones únicamente
para ilustrar el contrato**. Para embeddings reales, ajusta `dimensions` en el
índice y `APP_AZURE_SEARCH_VECTOR_DIMENSIONS` al modelo elegido. Los vectores de
documentos y preguntas deben proceder del mismo modelo y configuración.

El adaptador espera estos nombres de campos:

| Campo | Uso |
|-------|-----|
| `id` | Clave de Azure calculada a partir de `document_id` e ID del chunk. |
| `chunk_id` | ID original del chunk, que se devuelve al cliente. |
| `document_id` | Identificador del documento; debe ser filtrable. |
| `content` | Texto del fragmento. |
| `embedding` | Vector con dimensiones y perfil vectorial configurados. |
| `source` | Nombre o referencia al documento de origen. |
| `page` | Número de página opcional. |

La aplicación usa el plano de datos y no crea índices. El aprovisionamiento
del índice requiere un principal con permisos de administración de índices,
como `Search Service Contributor`; el rol de datos de la API no basta.

## Indexar chunks

```bash
curl -X POST http://localhost:8000/api/v1/documents/chunks \
  -H 'Content-Type: application/json' \
  -d '{
    "chunks": [{
      "id": "chunk-1",
      "document_id": "manual-1",
      "content": "Desconecta el equipo antes del mantenimiento.",
      "embedding": [0.1, 0.2, 0.3],
      "source": "manual.pdf",
      "page": 1
    }]
  }'
```

Respuesta `200`:

```json
{"indexed_chunks": 1}
```

Se admiten entre 1 y 1000 chunks por petición. Reenviar el mismo par
`document_id`/`id` reemplaza su contenido y metadatos. Un ID repetido dentro del
mismo documento y lote se rechaza con `422`.

Cada chunk se actualiza individualmente; el lote no es una transacción. Si
Azure acepta algunos chunks y rechaza otros, se devuelve `502` con código
`chunk_indexing_failed` y los IDs fallidos. Se puede reintentar el lote completo
con los mismos IDs. Si se cambia la fragmentación de un documento, los chunks
antiguos que ya no aparezcan en el nuevo lote no se eliminan automáticamente.

## Recuperar chunks

```bash
curl -X POST http://localhost:8000/api/v1/queries/search \
  -H 'Content-Type: application/json' \
  -d '{
    "embedding": [0.1, 0.2, 0.3],
    "top_k": 5,
    "document_id": "manual-1"
  }'
```

Ejemplo de respuesta `200` (la puntuación depende de Azure):

```json
{
  "matches": [{
    "id": "chunk-1",
    "document_id": "manual-1",
    "content": "Desconecta el equipo antes del mantenimiento.",
    "source": "manual.pdf",
    "page": 1,
    "score": 1.0
  }]
}
```

`top_k` admite valores entre 1 y 50. `document_id` es opcional; al omitirlo se
busca en todo el índice. El adaptador construye el filtro del documento y
escapa sus valores; el endpoint no acepta expresiones OData arbitrarias.
Los resultados no incluyen los embeddings. Una búsqueda sin coincidencias
devuelve `{"matches": []}`.

Los vectores vacíos, nulos o de dimensión incompatible se rechazan con `422`.
Un error de acceso al proveedor devuelve `503` con código
`vector_store_unavailable`, sin publicar el mensaje interno del SDK.

## Referencias

- [Cliente Python de Azure AI Search](https://learn.microsoft.com/en-us/python/api/azure-search-documents/azure.search.documents.searchclient?view=azure-python).
- [Acceso a Azure AI Search mediante roles](https://learn.microsoft.com/en-us/azure/search/search-security-rbac).
- [DefaultAzureCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential?view=azure-python).
