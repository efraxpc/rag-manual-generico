from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_answer_service, get_query_service
from app.schemas.queries import (
    RagAnswerRequest,
    RagAnswerResponse,
    VectorSearchRequest,
    VectorSearchResponse,
)
from app.services.answer import AnswerService
from app.services.query import QueryService

router = APIRouter()


@router.post(
    "/queries/answer",
    response_model=RagAnswerResponse,
    summary="Responder una pregunta usando los manuales indexados",
)
def answer_question(
    payload: RagAnswerRequest,
    service: Annotated[AnswerService, Depends(get_answer_service)],
) -> RagAnswerResponse:
    return RagAnswerResponse(**service.answer(payload).model_dump())


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
