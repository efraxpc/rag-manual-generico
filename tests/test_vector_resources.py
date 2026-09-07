from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.core import resources
from app.core.config import Settings
from app.integrations.azure_search import AzureSearchAdapter
from app.rag.contracts import VectorStore


def search_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        **{
            "azure_search_endpoint": "https://example.search.windows.net",
            "azure_search_index_name": "rag-chunks",
            "azure_search_vector_dimensions": 3,
            "azure_managed_identity_client_id": "test-client-id",
            **overrides,
        },
    )


def test_partial_search_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError, match="conjuntamente"):
        search_settings(azure_search_index_name=None)


def test_search_configuration_loads_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "APP_AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net"
    )
    monkeypatch.setenv("APP_AZURE_SEARCH_INDEX_NAME", "chunks")
    monkeypatch.setenv("APP_AZURE_SEARCH_VECTOR_DIMENSIONS", "3")
    monkeypatch.setenv("APP_AZURE_MANAGED_IDENTITY_CLIENT_ID", "identity-client-id")
    settings = Settings(_env_file=None)
    assert settings.azure_search_index_name == "chunks"
    assert settings.azure_search_vector_dimensions == 3
    assert settings.azure_managed_identity_client_id == "identity-client-id"


def test_clients_use_entra_and_close_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = MagicMock()
    client = MagicMock()
    credential.__enter__.return_value = credential
    client.__enter__.return_value = client
    credential_factory = Mock(return_value=credential)
    client_factory = Mock(return_value=client)
    monkeypatch.setattr(resources, "DefaultAzureCredential", credential_factory)
    monkeypatch.setattr(resources, "SearchClient", client_factory)

    with pytest.raises(RuntimeError, match="test failure"):
        with resources.open_vector_store(search_settings()) as store:
            assert isinstance(store, AzureSearchAdapter)
            raise RuntimeError("test failure")

    credential_factory.assert_called_once_with(
        managed_identity_client_id="test-client-id"
    )
    client_factory.assert_called_once_with(
        endpoint="https://example.search.windows.net/",
        index_name="rag-chunks",
        credential=credential,
    )
    client.__exit__.assert_called_once()
    credential.__exit__.assert_called_once()


def test_unconfigured_store_does_not_construct_azure_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_factory = Mock()
    monkeypatch.setattr(resources, "DefaultAzureCredential", credential_factory)
    settings = search_settings(
        azure_search_endpoint=None,
        azure_search_index_name=None,
        azure_search_vector_dimensions=None,
    )
    with resources.open_vector_store(settings) as store:
        assert store is None
    credential_factory.assert_not_called()


def test_lifespan_reuses_store_and_cleans_it_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = []
    store = Mock()

    @contextmanager
    def open_store(settings: Settings) -> Iterator[VectorStore]:
        events.append("open")
        try:
            yield store
        finally:
            events.append("close")

    monkeypatch.setattr(main, "open_vector_store", open_store)
    app = main.create_app()
    with TestClient(app) as client:
        assert app.state.vector_store is store
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 200
        assert events == ["open"]
    assert events == ["open", "close"]
    assert app.state.vector_store is None
