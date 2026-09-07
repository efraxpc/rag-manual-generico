"""Ventanas de caracteres deterministas, limitadas a cada página."""

from collections.abc import Sequence

from app.rag.models import Chunk
from app.services.extraction import TextPage

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def chunk_pages(
    pages: Sequence[TextPage], *, document_id: str, source: str
) -> list[Chunk]:
    chunks = []
    for page in pages:
        text = page.content.replace("\r\n", "\n").replace("\r", "\n").strip()
        for start in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
            content = text[start : start + CHUNK_SIZE].strip()
            if content:
                chunks.append(
                    Chunk(
                        id=f"page-{page.page or 0}-offset-{start}",
                        document_id=document_id,
                        content=content,
                        source=source,
                        page=page.page,
                    )
                )
            if start + CHUNK_SIZE >= len(text):
                break
    return chunks
