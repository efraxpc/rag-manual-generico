# RAG Manual API

Estructura base de una API con FastAPI, configuración por variables de entorno,
rutas versionadas y pruebas automatizadas.

## Requisitos

- Python 3.11 o superior

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Ejecución

Inicia la API y la interfaz juntas con:

```bash
./scripts/run_local.sh
```

El script usa los puertos `8000` y `8501` y detiene ambos servicios al pulsar
`Ctrl+C`. Puedes personalizarlos mediante `RAG_API_PORT` y `RAG_UI_PORT`:

```bash
RAG_API_PORT=8080 RAG_UI_PORT=8502 ./scripts/run_local.sh
```

Para reiniciar ambos servicios desde otra terminal, ejecuta:

```bash
./scripts/run_local.sh restart
```

Si no hay una instancia registrada, en Linux `restart` también detecta y detiene
instancias anteriores de este mismo script que no tengan archivo PID, y luego
inicia ambos servicios. Si un puerto está ocupado por otro proceso, el script
informa del conflicto y no inicia los servicios. El mensaje de disponibilidad
aparece cuando la API y la interfaz responden a sus comprobaciones de salud.

También puedes iniciar cada servicio por separado. Inicia la API en una
terminal:

```bash
uvicorn app.main:app --reload
```

En otra terminal, inicia la interfaz web:

```bash
streamlit run app/streamlit_app.py
```

La interfaz estará disponible en <http://localhost:8501>. Usa
`APP_API_BASE_URL` para apuntarla a una API que no se ejecute en
`http://localhost:8000`.

Esta versión permite cargar PDF con texto, TXT y Markdown desde Streamlit,
dividirlos en fragmentos y guardarlos en Azure AI Search con el botón
**Procesar y guardar**. Consulta la [guía de carga de archivos](docs/file-ingestion.md)
para preparar el índice de texto y configurar el entorno.

La API también permite indexar y recuperar chunks con embeddings precalculados
mediante el patrón Adapter. La generación de embeddings, el OCR y las respuestas
a preguntas siguen pendientes; los archivos cargados se guardan solo como texto.

Consulta la [guía del almacén vectorial](docs/vector-store.md) para configurar
Entra ID, preparar el índice y probar los endpoints:

- `POST /api/v1/documents/chunks`: indexación de chunks con embeddings.
- `POST /api/v1/queries/search`: recuperación vectorial de chunks.
- `POST /api/v1/documents/upload`: carga de un archivo y almacenamiento textual.

La documentación interactiva estará disponible en:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health check: <http://localhost:8000/api/v1/health>

## Pruebas y calidad

```bash
pytest
ruff check .
```

## Estructura

```text
app/
├── api/             # Rutas HTTP versionadas
├── core/            # Configuración y componentes compartidos
├── integrations/    # Adaptadores de proveedores: Azure AI Search
├── rag/             # Contratos y modelos del RAG
├── schemas/         # Modelos Pydantic de entrada y salida
├── services/        # Servicios de ingesta y consulta
├── main.py          # Creación de la API
└── streamlit_app.py # Interfaz web básica
tests/               # Pruebas automatizadas
docs/                # Arquitectura y uso del almacén vectorial
infrastructure/      # Infraestructura como código con Terraform
```

## Infraestructura en Azure

La base de Terraform está en `infrastructure/terraform`. Incluye autenticación
mediante Azure CLI, Azure Key Vault con RBAC y el despliegue de la API en Azure
Container Apps usando una imagen privada de Azure Container Registry. También
aprovisiona Azure AI Search con autenticación Entra ID y acceso RBAC para la
identidad administrada de la aplicación.
Consulta las instrucciones en
[`infrastructure/terraform/README.md`](infrastructure/terraform/README.md).
