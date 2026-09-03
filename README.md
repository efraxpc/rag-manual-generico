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

```bash
uvicorn app.main:app --reload
```

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
└── main.py          # Creación de la aplicación
tests/               # Pruebas automatizadas
infrastructure/      # Infraestructura como código con Terraform
```

## Infraestructura en Azure

La base de Terraform está en `infrastructure/terraform`. Incluye autenticación
mediante Azure CLI, Azure Key Vault con RBAC y el despliegue de la API en Azure
Container Apps usando una imagen privada de Azure Container Registry.
Consulta las instrucciones en
[`infrastructure/terraform/README.md`](infrastructure/terraform/README.md).
