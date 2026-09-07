"""Indexación de texto sin requerir campos vectoriales."""

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from azure.core.exceptions import AzureError
from azure.search.documents import SearchClient

from app.core.exceptions import (
    ApplicationError,
    ChunkIndexingError,
    TextStoreUnavailableError,
)
from app.rag.contracts import TextChunkStore
from app.rag.models import Chunk

INDEX_BATCH_SIZE = 1000
# Margen respecto a los 16 MB de Azure para serialización y envoltorio del SDK.
INDEX_BATCH_BYTES = 15_000_000


class AzureTextSearchAdapter(TextChunkStore):
    def __init__(self, client: SearchClient) -> None:
        self._client = client

    @staticmethod
    def _document(chunk: Chunk) -> dict[str, Any]:
        identity = json.dumps([chunk.document_id, chunk.id], ensure_ascii=False)
        return {
            "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "content": chunk.content,
            "source": chunk.source,
            "page": chunk.page,
        }

    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        batch: list[dict[str, Any]] = []
        batch_bytes = 0
        for chunk in chunks:
            document = self._document(chunk)
            # ensure_ascii=True ofrece una cota conservadora para texto Unicode.
            size = len(json.dumps(document).encode("utf-8")) + 64
            if size > INDEX_BATCH_BYTES:
                raise ApplicationError(
                    "Un fragmento supera el tamaño máximo de indexación.",
                    status_code=413,
                    code="chunk_too_large",
                )
            if batch and (
                len(batch) >= INDEX_BATCH_SIZE or batch_bytes + size > INDEX_BATCH_BYTES
            ):
                self._upload(batch)
                batch, batch_bytes = [], 0
            batch.append(document)
            batch_bytes += size
        if batch:
            self._upload(batch)

    def _upload(self, documents: list[dict[str, Any]]) -> None:
        try:
            results = self._client.upload_documents(documents=documents)
        except AzureError as exc:
            raise TextStoreUnavailableError() from exc
        succeeded = {result.key for result in results if result.succeeded}
        failed = [
            {"document_id": doc["document_id"], "chunk_id": doc["chunk_id"]}
            for doc in documents
            if doc["id"] not in succeeded
        ]
        if failed:
            raise ChunkIndexingError(failed)
