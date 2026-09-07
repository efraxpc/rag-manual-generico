"""Operaciones requeridas por el RAG, sin tipos del SDK de Azure."""

from collections.abc import Sequence
from typing import Protocol

from app.rag.models import EmbeddedChunk, SearchHit, VectorQuery


class VectorStore(Protocol):
    def index_chunks(self, chunks: Sequence[EmbeddedChunk]) -> None:
        """Inserta o reemplaza chunks identificados por documento e ID."""
        ...

    def search(self, query: VectorQuery) -> list[SearchHit]:
        """Recupera chunks relevantes, sin exponer detalles del proveedor."""
        ...
