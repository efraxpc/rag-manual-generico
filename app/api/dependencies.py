from typing import Annotated, cast

from fastapi import Depends, Request

from app.core.exceptions import ApplicationError
from app.rag.contracts import TextChunkStore, VectorStore
from app.services.file_ingestion import FileIngestionService
from app.services.ingestion import IngestionService
from app.services.query import QueryService


def get_text_store(request: Request) -> TextChunkStore:
    store = getattr(request.app.state, "text_store", None)
    if store is None:
        raise ApplicationError(
            "Configura el endpoint y el índice de texto de Azure AI Search.",
            status_code=503,
            code="text_store_not_configured",
        )
    return cast(TextChunkStore, store)


def get_file_ingestion_service(
    store: Annotated[TextChunkStore, Depends(get_text_store)],
) -> FileIngestionService:
    return FileIngestionService(store)


def get_vector_store(request: Request) -> VectorStore:
    store = getattr(request.app.state, "vector_store", None)
    if store is None:
        raise ApplicationError(
            "Configura el endpoint, el nombre de índice y las dimensiones de "
            "Azure AI Search para habilitar el almacén vectorial.",
            status_code=503,
            code="vector_store_not_configured",
        )
    return cast(VectorStore, store)


def get_ingestion_service(
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> IngestionService:
    return IngestionService(vector_store)


def get_query_service(
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> QueryService:
    return QueryService(vector_store)
