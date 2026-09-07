from functools import lru_cache
from typing import Self

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAG Manual API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    docs_enabled: bool = True
    api_v1_prefix: str = "/api/v1"
    api_base_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:3000"]
    azure_search_endpoint: HttpUrl | None = None
    azure_search_index_name: str | None = Field(default=None, min_length=1)
    azure_search_text_index_name: str | None = Field(default=None, min_length=1)
    azure_search_vector_dimensions: int | None = Field(default=None, ge=1)
    azure_managed_identity_client_id: str | None = Field(default=None, min_length=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_search_configuration(self) -> Self:
        vector_values = (
            self.azure_search_index_name,
            self.azure_search_vector_dimensions,
        )
        if any(value is not None for value in vector_values) and not all(
            value is not None for value in (self.azure_search_endpoint, *vector_values)
        ):
            raise ValueError(
                "Configura APP_AZURE_SEARCH_ENDPOINT, APP_AZURE_SEARCH_INDEX_NAME y "
                "APP_AZURE_SEARCH_VECTOR_DIMENSIONS conjuntamente."
            )
        has_index = (
            self.azure_search_index_name is not None
            or self.azure_search_text_index_name is not None
        )
        if (self.azure_search_endpoint is not None) != has_index:
            raise ValueError(
                "Configura conjuntamente el endpoint y al menos un índice."
            )
        if (
            self.azure_search_text_index_name is not None
            and self.azure_search_text_index_name == self.azure_search_index_name
        ):
            raise ValueError("Los índices textual y vectorial deben ser distintos.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
