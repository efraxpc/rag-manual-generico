from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile

from app.api.dependencies import get_file_ingestion_service, get_ingestion_service
from app.schemas.documents import (
    IndexChunksRequest,
    IndexChunksResponse,
    UploadDocumentResponse,
)
from app.services.file_ingestion import FileIngestionService
from app.services.ingestion import IngestionService

router = APIRouter()


@router.post(
    "/documents/upload",
    response_model=UploadDocumentResponse,
    summary="Extraer, dividir y guardar un archivo como fragmentos de texto",
)
def upload_document(
    file: UploadFile,
    service: Annotated[FileIngestionService, Depends(get_file_ingestion_service)],
) -> UploadDocumentResponse:
    try:
        result = service.ingest(file.filename, file.file)
    finally:
        file.file.close()
    return UploadDocumentResponse(
        document_id=result.document_id,
        source=result.source,
        indexed_chunks=result.indexed_chunks,
        warnings=result.warnings,
    )


@router.post(
    "/documents/chunks",
    response_model=IndexChunksResponse,
    summary="Indexar chunks con embeddings ya calculados",
)
def index_chunks(
    payload: IndexChunksRequest,
    service: Annotated[IngestionService, Depends(get_ingestion_service)],
) -> IndexChunksResponse:
    return IndexChunksResponse(indexed_chunks=service.index_chunks(payload.chunks))
