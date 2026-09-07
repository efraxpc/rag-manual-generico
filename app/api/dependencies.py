from typing import Annotated, cast

from fastapi import Depends, Request

from app.core.exceptions import ApplicationError
from app.rag.contracts import VectorStore
from app.services.ingestion import IngestionService
from app.services.query import QueryService


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
