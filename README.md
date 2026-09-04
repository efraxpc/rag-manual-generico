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

Inicia la API en una terminal:

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

Esta versión permite seleccionar un manual, preparar una consulta y comprobar
la conexión con la API. El procesamiento RAG se conectará cuando exista el
endpoint de consultas correspondiente.

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
├── schemas/         # Modelos Pydantic de entrada y salida
├── main.py          # Creación de la API
└── streamlit_app.py # Interfaz web básica
tests/               # Pruebas automatizadas
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
