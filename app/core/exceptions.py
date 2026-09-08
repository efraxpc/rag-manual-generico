import logging
from typing import Any

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Uvicorn ya configura este logger para escribir en la consola del backend.
logger = logging.getLogger("uvicorn.error")


class ApplicationError(Exception):
    """Error controlado que puede exponerse al cliente."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "application_error",
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        self.headers = headers
        super().__init__(message)


class VectorStoreUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "No se pudo acceder al almacén vectorial. Comprueba la configuración, "
            "la existencia del índice y los permisos de Entra ID.",
            status_code=503,
            code="vector_store_unavailable",
        )


class ChunkIndexingError(ApplicationError):
    def __init__(self, failed_chunks: list[dict[str, str]]) -> None:
        super().__init__(
            "No se pudieron indexar todos los chunks. Algunos pueden haberse guardado; "
            "se puede reintentar el lote con los mismos IDs.",
            status_code=502,
            code="chunk_indexing_failed",
            details={"failed_chunks": failed_chunks},
        )


class TextStoreUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "No se pudo acceder al índice de texto. Comprueba su existencia y "
            "los permisos de Entra ID. Algunos fragmentos pueden haberse guardado; "
            "puedes reintentar con el mismo archivo.",
            status_code=503,
            code="text_store_unavailable",
        )


class SearchAccessDeniedError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "Tu usuario no tiene permisos para esta operación en Azure AI Search. "
            "Para cargar documentos necesitas Search Index Data Contributor.",
            status_code=403,
            code="search_access_denied",
        )


async def application_error_handler(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    server_error = exc.status_code >= 500
    logger.log(
        logging.ERROR if server_error else logging.WARNING,
        "%s %s -> %s [%s] %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.code,
        exc.message,
        # Conserva la causa del SDK enlazada con `raise ... from exc`.
        exc_info=(type(exc), exc, exc.__traceback__) if server_error else None,
    )
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Los errores completos incluyen valores de entrada; solo registramos
    # la ubicación y el tipo, sin el archivo, cuerpo, cabeceras ni query string.
    errors = [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()]
    logger.warning(
        "%s %s -> 422 [request_validation_error] %s",
        request.method,
        request.url.path,
        errors,
    )
    return await request_validation_exception_handler(request, exc)
