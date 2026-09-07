"""Datos que circulan entre los servicios y el almacén vectorial."""

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=512)
    document_id: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1)
    source: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)


class EmbeddedChunk(Chunk):
    embedding: list[FiniteFloat] = Field(min_length=1)


class VectorQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    embedding: list[FiniteFloat] = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    document_id: str | None = Field(default=None, min_length=1, max_length=512)


class SearchHit(Chunk):
    score: FiniteFloat
