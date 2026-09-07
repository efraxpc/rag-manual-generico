from collections.abc import Sequence

from app.core.exceptions import ApplicationError
from app.rag.contracts import VectorStore
from app.rag.models import EmbeddedChunk


class IngestionService:
    """Indexa chunks ya preparados; la extracción y vectorización son previas."""

    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    def index_chunks(self, chunks: Sequence[EmbeddedChunk]) -> int:
        identities = {(chunk.document_id, chunk.id) for chunk in chunks}
        if len(identities) != len(chunks):
            raise ApplicationError(
                "El lote contiene IDs de chunk repetidos dentro del mismo documento.",
                status_code=422,
                code="duplicate_chunk_id",
            )
        self._vector_store.index_chunks(chunks)
        return len(chunks)
