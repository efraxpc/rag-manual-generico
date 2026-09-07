"""Construcción y cierre de las dependencias externas de la aplicación."""

from collections.abc import Iterator
from contextlib import contextmanager

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

from app.core.config import Settings
from app.integrations.azure_search import AzureSearchAdapter
from app.integrations.azure_text_search import AzureTextSearchAdapter
from app.rag.contracts import TextChunkStore, VectorStore


@contextmanager
def open_vector_store(settings: Settings) -> Iterator[VectorStore | None]:
    if settings.azure_search_index_name is None:
        yield None
        return

    assert settings.azure_search_endpoint is not None
    assert settings.azure_search_vector_dimensions is not None

    with (
        DefaultAzureCredential(
            managed_identity_client_id=settings.azure_managed_identity_client_id
        ) as credential,
        SearchClient(
            endpoint=str(settings.azure_search_endpoint),
            index_name=settings.azure_search_index_name,
            credential=credential,
        ) as client,
    ):
        yield AzureSearchAdapter(
            client, vector_dimensions=settings.azure_search_vector_dimensions
        )


@contextmanager
def open_text_store(settings: Settings) -> Iterator[TextChunkStore | None]:
    if settings.azure_search_text_index_name is None:
        yield None
        return
    assert settings.azure_search_endpoint is not None
    with (
        DefaultAzureCredential(
            managed_identity_client_id=settings.azure_managed_identity_client_id
        ) as credential,
        SearchClient(
            endpoint=str(settings.azure_search_endpoint),
            index_name=settings.azure_search_text_index_name,
            credential=credential,
        ) as client,
    ):
        yield AzureTextSearchAdapter(client)
