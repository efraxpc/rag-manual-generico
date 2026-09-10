from functools import lru_cache
from typing import Self
from uuid import UUID

from pydantic import Field, HttpUrl, SecretStr, model_validator
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
    azure_openai_endpoint: HttpUrl | None = None
    azure_openai_chat_deployment: str | None = Field(default=None, min_length=1)
    azure_openai_judge_deployment: str | None = Field(default=None, min_length=1)
    rag_generation_timeout_seconds: float = Field(default=60, gt=0, le=300)
    llm_judge_timeout_seconds: float = Field(default=60, gt=0, le=300)
    azure_managed_identity_client_id: str | None = Field(default=None, min_length=1)
    entra_tenant_id: UUID | None = None
    entra_api_client_id: UUID | None = None
    entra_api_client_secret: SecretStr | None = Field(default=None, min_length=1)
    entra_frontend_client_id: UUID | None = None

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

    @model_validator(mode="after")
    def validate_judge_configuration(self) -> Self:
        deployments = (
            self.azure_openai_chat_deployment,
            self.azure_openai_judge_deployment,
        )
        if self.azure_openai_endpoint is None and any(
            deployment is not None for deployment in deployments
        ):
            raise ValueError(
                "Configura APP_AZURE_OPENAI_ENDPOINT conjuntamente con los "
                "despliegues de Azure OpenAI que utilices."
            )
        if self.azure_openai_endpoint is not None and not any(
            deployment is not None for deployment in deployments
        ):
            raise ValueError(
                "Configura APP_AZURE_OPENAI_ENDPOINT conjuntamente con al menos "
                "APP_AZURE_OPENAI_CHAT_DEPLOYMENT o "
                "APP_AZURE_OPENAI_JUDGE_DEPLOYMENT."
            )
        if self.azure_openai_endpoint is not None and (
            self.azure_openai_endpoint.scheme != "https"
            or self.azure_openai_endpoint.path not in {"", "/"}
            or self.azure_openai_endpoint.query is not None
            or self.azure_openai_endpoint.fragment is not None
        ):
            raise ValueError(
                "APP_AZURE_OPENAI_ENDPOINT debe ser una URL HTTPS de recurso, "
                "sin ruta ni query."
            )
        return self

    @property
    def entra_configured(self) -> bool:
        return self.entra_tenant_id is not None

    @model_validator(mode="after")
    def validate_entra_configuration(self) -> Self:
        values = (
            self.entra_tenant_id,
            self.entra_api_client_id,
            self.entra_api_client_secret,
            self.entra_frontend_client_id,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError(
                "Configura conjuntamente las cuatro variables APP_ENTRA_*."
            )
        if (
            self.entra_configured
            and self.entra_api_client_id == self.entra_frontend_client_id
        ):
            raise ValueError(
                "Usa registros de aplicación distintos para API y frontend."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
