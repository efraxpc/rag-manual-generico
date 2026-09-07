from pydantic import BaseModel, ConfigDict, Field

from app.rag.models import EmbeddedChunk


class IndexChunksRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunks: list[EmbeddedChunk] = Field(min_length=1, max_length=1000)


class IndexChunksResponse(BaseModel):
    indexed_chunks: int


class UploadDocumentResponse(BaseModel):
    document_id: str
    source: str
    indexed_chunks: int
    warnings: list[str]
