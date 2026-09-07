from app.rag.contracts import VectorStore
from app.rag.models import SearchHit, VectorQuery


class QueryService:
    """Recupera contexto vectorial; todavía no genera respuestas con un LLM."""

    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    def search(self, query: VectorQuery) -> list[SearchHit]:
        return self._vector_store.search(query)
