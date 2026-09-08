from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.auth import EntraTokenVerifier
from app.core.config import get_settings
from app.core.exceptions import (
    ApplicationError,
    application_error_handler,
    validation_error_handler,
)


def create_app() -> FastAPI:
    """Construye y configura la aplicación."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    application.state.settings = settings
    application.state.token_verifier = (
        EntraTokenVerifier(settings) if settings.entra_configured else None
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(ApplicationError, application_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    return application


app = create_app()
