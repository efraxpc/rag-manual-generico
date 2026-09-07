"""Orquesta validación, extracción, chunking e indexación de un archivo."""

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

from app.core.exceptions import ApplicationError
from app.rag.contracts import TextChunkStore
from app.services.chunking import chunk_pages
from app.services.extraction import extract_text, invalid_document

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


@dataclass(frozen=True)
class IngestionResult:
    document_id: str
    source: str
    indexed_chunks: int
    warnings: list[str]


class FileIngestionService:
    def __init__(self, store: TextChunkStore) -> None:
        self._store = store

    def ingest(self, filename: str | None, file: BinaryIO) -> IngestionResult:
        source = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not source or len(source) > 255:
            raise invalid_document("El nombre debe tener entre 1 y 255 caracteres.")
        extension = PurePosixPath(source).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ApplicationError(
                "Formatos admitidos: PDF, TXT y Markdown.",
                status_code=415,
                code="unsupported_file_type",
            )
        data = file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise ApplicationError(
                "El archivo supera el límite de 10 MiB.",
                status_code=413,
                code="file_too_large",
            )
        pages, warnings = extract_text(data, extension)
        # El separador evita ambigüedades entre nombre y contenido.
        document_id = hashlib.sha256(source.encode("utf-8") + b"\0" + data).hexdigest()
        chunks = chunk_pages(pages, document_id=document_id, source=source)
        self._store.index_chunks(chunks)
        return IngestionResult(document_id, source, len(chunks), warnings)
