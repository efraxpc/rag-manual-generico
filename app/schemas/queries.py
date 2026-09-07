from pydantic import BaseModel

from app.rag.models import SearchHit, VectorQuery


class VectorSearchRequest(VectorQuery):
    """Consulta mediante un embedding calculado previamente."""


class VectorSearchResponse(BaseModel):
    matches: list[SearchHit]
