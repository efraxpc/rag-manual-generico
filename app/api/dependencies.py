from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from app.core.auth import AuthenticatedUser, require_user
from app.core.exceptions import ApplicationError
from app.core.resources import open_text_store, open_vector_store
from app.rag.contracts import TextChunkStore, VectorStore
from app.services.file_ingestion import FileIngestionService
from app.services.ingestion import IngestionService
from app.services.query import QueryService


def get_text_store(
    request: Request, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> Iterator[TextChunkStore]:
    with open_text_store(
        request.app.state.settings, user_assertion=user.assertion
    ) as store:
        if store is None:
            raise ApplicationError(
                "Configura el endpoint y el índice de texto de Azure AI Search.",
                status_code=503,
                code="text_store_not_configured",
            )
        yield store


def get_file_ingestion_service(
    store: Annotated[TextChunkStore, Depends(get_text_store)],
) -> FileIngestionService:
    return FileIngestionService(store)


def get_vector_store(
    request: Request, user: Annotated[AuthenticatedUser, Depends(require_user)]
) -> Iterator[VectorStore]:
    with open_vector_store(
        request.app.state.settings, user_assertion=user.assertion
    ) as store:
        if store is None:
            raise ApplicationError(
                "Configura el endpoint, el índice y las dimensiones de "
                "Azure AI Search.",
                status_code=503,
                code="vector_store_not_configured",
            )
        yield store


def get_ingestion_service(
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> IngestionService:
    return IngestionService(vector_store)


def get_query_service(
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
) -> QueryService:
    return QueryService(vector_store)
