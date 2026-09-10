"""Operaciones requeridas por el RAG, sin tipos del SDK de Azure."""

from collections.abc import Sequence
from typing import Protocol

from app.rag.models import Chunk, EmbeddedChunk, SearchHit, TextQuery, VectorQuery


class TextChunkStore(Protocol):
    def index_chunks(self, chunks: Sequence[Chunk]) -> None:
        """Inserta o reemplaza fragmentos de texto sin embeddings."""
        ...

    def search(self, query: TextQuery) -> list[SearchHit]:
        """Recupera fragmentos mediante la pregunta en lenguaje natural."""
        ...


class VectorStore(Protocol):
    def index_chunks(self, chunks: Sequence[EmbeddedChunk]) -> None:
        """Inserta o reemplaza chunks identificados por documento e ID."""
        ...

    def search(self, query: VectorQuery) -> list[SearchHit]:
        """Recupera chunks relevantes, sin exponer detalles del proveedor."""
        ...


class TextCompletionClient(Protocol):
    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Genera texto a partir de mensajes independientes del proveedor."""
        ...
