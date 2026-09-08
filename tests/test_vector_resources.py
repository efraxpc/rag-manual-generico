from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.core import resources
from app.core.config import Settings
from app.integrations.azure_search import AzureSearchAdapter
from tests.auth_helpers import entra_settings


def search_settings(**overrides: object) -> Settings:
    return entra_settings(
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
    monkeypatch.setattr(resources, "OnBehalfOfCredential", credential_factory)
    monkeypatch.setattr(resources, "SearchClient", client_factory)

    with pytest.raises(RuntimeError, match="test failure"):
        with resources.open_vector_store(
            search_settings(), user_assertion="user-token"
        ) as store:
            assert isinstance(store, AzureSearchAdapter)
            raise RuntimeError("test failure")

    credential_factory.assert_called_once_with(
        tenant_id=str(search_settings().entra_tenant_id),
        client_id=str(search_settings().entra_api_client_id),
        client_secret="test-api-secret",
        user_assertion="user-token",
    )
    client_factory.assert_called_once_with(
        endpoint="https://example.search.windows.net/",
        index_name="rag-chunks",
        credential=credential,
    )
    client.__exit__.assert_called_once()
    credential.__exit__.assert_called_once()
    credential.get_token.assert_called_once_with(resources.SEARCH_SCOPE)


def test_unconfigured_store_does_not_construct_azure_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_factory = Mock()
    monkeypatch.setattr(resources, "OnBehalfOfCredential", credential_factory)
    settings = search_settings(
        azure_search_endpoint=None,
        azure_search_index_name=None,
        azure_search_vector_dimensions=None,
        azure_search_text_index_name=None,
    )
    with resources.open_vector_store(settings, user_assertion="user-token") as store:
        assert store is None
    credential_factory.assert_not_called()


def test_startup_does_not_create_a_shared_user_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_factory = Mock()
    monkeypatch.setattr(resources, "OnBehalfOfCredential", credential_factory)
    monkeypatch.setattr(main, "get_settings", search_settings)
    app = main.create_app()
    with TestClient(app) as client:
        assert not hasattr(app.state, "vector_store")
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 200
    credential_factory.assert_not_called()
