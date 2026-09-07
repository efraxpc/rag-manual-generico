from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_ingestion_service
from app.schemas.documents import IndexChunksRequest, IndexChunksResponse
from app.services.ingestion import IngestionService

router = APIRouter()


@router.post(
    "/documents/chunks",
    response_model=IndexChunksResponse,
    summary="Indexar chunks con embeddings ya calculados",
)
def index_chunks(
    payload: IndexChunksRequest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IndexChunksResponse:
    return IndexChunksResponse(indexed_chunks=service.index_chunks(payload.chunks))
