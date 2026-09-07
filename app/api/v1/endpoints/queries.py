from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_query_service
from app.schemas.queries import VectorSearchRequest, VectorSearchResponse
from app.services.query import QueryService

router = APIRouter()


@router.post(
    "/queries/search",
    response_model=VectorSearchResponse,
    summary="Recuperar chunks mediante búsqueda vectorial",
)
def search_chunks(
    payload: VectorSearchRequest,
    service: Annotated[QueryService, Depends(get_query_service)],
) -> VectorSearchResponse:
    return VectorSearchResponse(matches=service.search(payload))
