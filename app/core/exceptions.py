from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApplicationError(Exception):
    """Error controlado que puede exponerse al cliente."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "application_error",
        details: Any | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
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


async def application_error_handler(
    _request: Request, exc: ApplicationError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )
