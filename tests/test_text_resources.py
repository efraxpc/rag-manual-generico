from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.api import dependencies
from app.core import resources
from app.core.auth import require_user
from app.core.config import Settings
from app.integrations.azure_openai_chat import AZURE_AI_SCOPE
from app.integrations.azure_text_search import AzureTextSearchAdapter
from app.rag.contracts import TextChunkStore
from tests.auth_helpers import authenticated_user, entra_settings


def text_settings(**overrides: object) -> Settings:
    return entra_settings(
        **{
            "azure_search_endpoint": "https://example.search.windows.net",
            "azure_search_text_index_name": "rag-text-chunks",
            "azure_search_index_name": None,
            "azure_search_vector_dimensions": None,
            "azure_managed_identity_client_id": "test-client-id",
            **overrides,
        },
    )


def test_text_configuration_does_not_require_vectors() -> None:
    settings = text_settings()
    assert settings.azure_search_vector_dimensions is None
    with resources.open_vector_store(settings, user_assertion="user-token") as vector:
        assert vector is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"azure_search_endpoint": None},
        {"azure_search_text_index_name": None},
        {"azure_search_index_name": "rag-chunks"},
        {"azure_search_vector_dimensions": 3},
        {
            "azure_search_index_name": "rag-text-chunks",
            "azure_search_vector_dimensions": 3,
        },
    ],
)
def test_invalid_combinations(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        text_settings(**overrides)


def test_text_and_vector_can_be_configured_together() -> None:
    assert text_settings(
        azure_search_index_name="rag-chunks", azure_search_vector_dimensions=3
    ).azure_search_text_index_name


def test_text_index_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "APP_AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net"
    )
    monkeypatch.setenv("APP_AZURE_SEARCH_TEXT_INDEX_NAME", "text-chunks")
    settings = Settings(
        _env_file=None,
        azure_search_index_name=None,
        azure_search_vector_dimensions=None,
    )
    assert settings.azure_search_text_index_name == "text-chunks"


def test_text_clients_use_identity_and_close(monkeypatch: pytest.MonkeyPatch) -> None:
    credential, client = MagicMock(), MagicMock()
    credential.__enter__.return_value = credential
    client.__enter__.return_value = client
    credential_factory = Mock(return_value=credential)
    client_factory = Mock(return_value=client)
    monkeypatch.setattr(resources, "OnBehalfOfCredential", credential_factory)
    monkeypatch.setattr(resources, "SearchClient", client_factory)
    with pytest.raises(RuntimeError):
        with resources.open_text_store(
            text_settings(), user_assertion="user-token"
        ) as store:
            assert isinstance(store, AzureTextSearchAdapter)
            raise RuntimeError()
    credential_factory.assert_called_once_with(
        tenant_id=str(text_settings().entra_tenant_id),
        client_id=str(text_settings().entra_api_client_id),
        client_secret="test-api-secret",
        user_assertion="user-token",
    )
    client_factory.assert_called_once_with(
        endpoint="https://example.search.windows.net/",
        index_name="rag-text-chunks",
        credential=credential,
    )
    client.__exit__.assert_called_once()
    credential.__exit__.assert_called_once()


def test_unconfigured_text_store_does_not_create_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock()
    monkeypatch.setattr(resources, "SearchClient", factory)
    with resources.open_text_store(
        text_settings(
            azure_search_endpoint=None,
            azure_search_text_index_name=None,
        ),
        user_assertion="user-token",
    ) as store:
        assert store is None
    factory.assert_not_called()


def test_chat_client_uses_user_obo_identity_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential, http_client, chat_client = MagicMock(), MagicMock(), Mock()
    credential.__enter__.return_value = credential
    http_client.__enter__.return_value = http_client
    credential_factory = Mock(return_value=credential)
    http_factory = Mock(return_value=http_client)
    chat_factory = Mock(return_value=chat_client)
    monkeypatch.setattr(resources, "OnBehalfOfCredential", credential_factory)
    monkeypatch.setattr(resources.httpx, "Client", http_factory)
    monkeypatch.setattr(resources, "AzureOpenAIChatClient", chat_factory)
    settings = text_settings(
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="candidate-v1",
    )

    with resources.open_user_chat_client(
        settings, user_assertion="user-token"
    ) as client:
        assert client is chat_client

    credential.get_token.assert_called_once_with(AZURE_AI_SCOPE)
    chat_factory.assert_called_once_with(
        endpoint="https://example.openai.azure.com/",
        deployment="candidate-v1",
        credential=credential,
        http_client=http_client,
    )
    http_client.__exit__.assert_called_once()
    credential.__exit__.assert_called_once()


def test_unconfigured_chat_does_not_create_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = Mock()
    monkeypatch.setattr(resources, "OnBehalfOfCredential", factory)
    with resources.open_user_chat_client(
        text_settings(), user_assertion="user-token"
    ) as client:
        assert client is None
    factory.assert_not_called()


def test_text_only_lifespan_and_vector_503(monkeypatch: pytest.MonkeyPatch) -> None:
    store = Mock()
    closed = []

    @contextmanager
    def open_store(
        settings: Settings, *, user_assertion: str
    ) -> Iterator[TextChunkStore]:
        assert user_assertion == authenticated_user().assertion
        try:
            yield store
        finally:
            closed.append(True)

    monkeypatch.setattr(main, "get_settings", text_settings)
    monkeypatch.setattr(dependencies, "open_text_store", open_store)
    app = main.create_app()
    app.dependency_overrides[require_user] = authenticated_user
    with TestClient(app) as client:
        assert not hasattr(app.state, "text_store")
        assert (
            client.post(
                "/api/v1/documents/upload", files={"file": ("a.txt", b"Text")}
            ).status_code
            == 200
        )
        response = client.post("/api/v1/queries/search", json={"embedding": [1.0]})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "vector_store_not_configured"
    assert closed == [True]
    assert not hasattr(app.state, "text_store")
