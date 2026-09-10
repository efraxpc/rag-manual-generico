from pydantic import BaseModel

from app.rag.models import RagAnswer, SearchHit, TextQuery, VectorQuery


class VectorSearchRequest(VectorQuery):
    """Consulta mediante un embedding calculado previamente."""


class VectorSearchResponse(BaseModel):
    matches: list[SearchHit]


class RagAnswerRequest(TextQuery):
    """Pregunta en lenguaje natural para el índice textual."""


class RagAnswerResponse(RagAnswer):
    """Respuesta fundamentada y contexto que la produjo."""
