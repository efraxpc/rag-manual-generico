"""Traducción entre el contrato VectorStore y Azure AI Search."""

import hashlib
import json
from collections.abc import Sequence

from azure.core.exceptions import AzureError
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from pydantic import ValidationError

from app.core.exceptions import (
    ApplicationError,
    ChunkIndexingError,
    SearchAccessDeniedError,
    VectorStoreUnavailableError,
)
from app.rag.contracts import VectorStore
from app.rag.models import EmbeddedChunk, SearchHit, VectorQuery

INDEX_BATCH_SIZE = 1000


class AzureSearchAdapter(VectorStore):
    def __init__(self, client: SearchClient, *, vector_dimensions: int) -> None:
        if vector_dimensions < 1:
            raise ValueError("vector_dimensions debe ser positivo")
        self._client = client
        self._vector_dimensions = vector_dimensions

    @staticmethod
    def _document_key(chunk: EmbeddedChunk) -> str:
        # El hash mantiene una clave válida y estable para cualquier ID Unicode.
        identity = json.dumps([chunk.document_id, chunk.id], ensure_ascii=False)
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _validate_embedding(self, embedding: Sequence[float]) -> None:
        if len(embedding) != self._vector_dimensions:
            raise ApplicationError(
                "La dimensión del embedding no coincide con la del índice.",
                status_code=422,
                code="invalid_embedding_dimensions",
                details={
                    "expected": self._vector_dimensions,
                    "received": len(embedding),
                },
            )
        if not any(embedding):
            raise ApplicationError(
                "El embedding no puede ser un vector nulo.",
                status_code=422,
                code="invalid_embedding",
            )

    def index_chunks(self, chunks: Sequence[EmbeddedChunk]) -> None:
        # Validamos todo el lote antes de realizar la primera escritura.
        for chunk in chunks:
            self._validate_embedding(chunk.embedding)

        for offset in range(0, len(chunks), INDEX_BATCH_SIZE):
            batch = chunks[offset : offset + INDEX_BATCH_SIZE]
            documents = [
                {
                    "id": self._document_key(chunk),
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "content": chunk.content,
                    "embedding": chunk.embedding,
                    "source": chunk.source,
                    "page": chunk.page,
                }
                for chunk in batch
            ]
            try:
                # upload reemplaza el documento completo si la clave ya existe.
                results = self._client.upload_documents(documents=documents)
            except AzureError as exc:
                if getattr(exc, "status_code", None) == 403:
                    raise SearchAccessDeniedError() from exc
                raise VectorStoreUnavailableError() from exc

            succeeded = {result.key for result in results if result.succeeded}
            failed = [
                {"document_id": chunk.document_id, "chunk_id": chunk.id}
                for chunk in batch
                if self._document_key(chunk) not in succeeded
            ]
            if failed:
                raise ChunkIndexingError(failed)

    def search(self, query: VectorQuery) -> list[SearchHit]:
        self._validate_embedding(query.embedding)
        document_filter = None
        if query.document_id is not None:
            # Los literales OData escapan comillas simples duplicándolas.
            document_id = query.document_id.replace("'", "''")
            document_filter = f"document_id eq '{document_id}'"

        try:
            results = self._client.search(
                search_text=None,
                vector_queries=[
                    VectorizedQuery(
                        vector=query.embedding,
                        k_nearest_neighbors=query.top_k,
                        fields="embedding",
                    )
                ],
                filter=document_filter,
                vector_filter_mode="preFilter",
                top=query.top_k,
                select=["chunk_id", "document_id", "content", "source", "page"],
            )
            return [
                SearchHit(
                    id=result["chunk_id"],
                    document_id=result["document_id"],
                    content=result["content"],
                    source=result["source"],
                    page=result.get("page"),
                    score=result["@search.score"],
                )
                for result in results
            ]
        except AzureError as exc:
            # La petición también puede fallar durante la paginación del SDK.
            if getattr(exc, "status_code", None) == 403:
                raise SearchAccessDeniedError() from exc
            raise VectorStoreUnavailableError() from exc
        except (KeyError, TypeError, ValidationError) as exc:
            raise ApplicationError(
                "El almacén vectorial devolvió una respuesta incompatible.",
                status_code=502,
                code="invalid_vector_store_response",
            ) from exc
