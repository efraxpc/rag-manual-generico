import json
import time
from collections.abc import Iterator
from unittest.mock import MagicMock, Mock

import jwt
import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.search.documents.models import IndexingResult
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWKClientConnectionError
from pydantic import ValidationError

from app import main
from app.core import auth, resources
from app.core.auth import EntraTokenVerifier
from tests.auth_helpers import (
    API_CLIENT,
    FRONTEND_CLIENT,
    OTHER_USER_ID,
    TENANT,
    USER_ID,
    entra_settings,
)


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(private_key: rsa.RSAPrivateKey, **overrides: object) -> str:
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": API_CLIENT,
        "tid": TENANT,
        "oid": USER_ID,
        "sub": "user-subject",
        "azp": FRONTEND_CLIENT,
        "ver": "2.0",
        "scp": "access_as_user",
        "iat": now - 60,
        "nbf": now - 60,
        "exp": now + 3600,
        **overrides,
    }
    return jwt.encode(
        claims, private_key, algorithm="RS256", headers={"kid": "test-key"}
    )


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, private_key: rsa.RSAPrivateKey
) -> Iterator[TestClient]:
    public_jwk = json.loads(
        jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key())
    )
    public_jwk.update(kid="test-key", use="sig", alg="RS256")
    # Verifica firmas de verdad y evita toda llamada de red al obtener claves.
    monkeypatch.setattr(
        auth.PyJWKClient, "fetch_data", lambda self: {"keys": [public_jwk]}
    )
    monkeypatch.setattr(main, "get_settings", entra_settings)
    with TestClient(main.create_app()) as client:
        yield client


def upload(client: TestClient, token: str | None):
    return client.post(
        "/api/v1/documents/upload",
        files={"file": ("a.txt", b"Text")},
        headers={"Authorization": f"Bearer {token}"} if token is not None else {},
    )


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_anonymous_or_malformed_tokens_are_401(
    client: TestClient, token: str | None
) -> None:
    response = upload(client, token)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert client.get("/api/v1/health").status_code == 200


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/v1/documents/chunks", {"chunks": []}),
        ("/api/v1/queries/search", {"embedding": [1, 2, 3]}),
    ],
)
def test_vector_endpoints_also_require_login(
    client: TestClient, path: str, payload: dict
) -> None:
    assert client.post(path, json=payload).status_code == 401


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"exp": 1}, 401),
        ({"nbf": 4_000_000_000}, 401),
        ({"aud": FRONTEND_CLIENT}, 401),
        ({"aud": "https://search.azure.com"}, 401),
        ({"iss": "https://attacker.invalid"}, 401),
        ({"tid": OTHER_USER_ID}, 401),
        ({"ver": "1.0"}, 401),
        ({"oid": "not-a-user"}, 401),
        ({"scp": None, "roles": ["access_as_user"]}, 403),
        ({"scp": "other_permission"}, 403),
        ({"azp": OTHER_USER_ID}, 403),
    ],
)
def test_rejects_invalid_claims_before_creating_search_credentials(
    client: TestClient,
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict,
    status: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory = Mock()
    monkeypatch.setattr(resources, "OnBehalfOfCredential", factory)
    token = make_token(private_key, **changes)
    response = upload(client, token)
    assert response.status_code == status
    factory.assert_not_called()
    assert token not in response.text and token not in caplog.text


def test_rejects_wrong_signature(client: TestClient) -> None:
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert upload(client, make_token(wrong_key)).status_code == 401


def test_key_endpoint_unavailable_is_503(
    client: TestClient, private_key: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        auth.PyJWKClient,
        "fetch_data",
        Mock(side_effect=PyJWKClientConnectionError("network failed")),
    )
    response = upload(client, make_token(private_key))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "identity_provider_unavailable"


def azure_doubles(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    def new_credential(**kwargs: object) -> MagicMock:
        credential = MagicMock()
        credential.__enter__.return_value = credential
        credential.assertion = kwargs["user_assertion"]
        return credential

    def new_client(**kwargs: object) -> MagicMock:
        client = MagicMock()
        client.__enter__.return_value = client
        client.credential = kwargs["credential"]
        client.upload_documents.side_effect = lambda documents: [
            IndexingResult.deserialize({"key": doc["id"], "status": True})
            for doc in documents
        ]
        return client

    credentials = Mock(side_effect=new_credential)
    clients = Mock(side_effect=new_client)
    monkeypatch.setattr(resources, "OnBehalfOfCredential", credentials)
    monkeypatch.setattr(resources, "SearchClient", clients)
    return credentials, clients


def test_two_users_receive_separate_credentials_and_clients(
    client: TestClient,
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials, clients = azure_doubles(monkeypatch)
    first = make_token(private_key)
    second = make_token(private_key, oid=OTHER_USER_ID)
    assert upload(client, first).status_code == 200
    assert upload(client, second).status_code == 200
    assert [call.kwargs["user_assertion"] for call in credentials.call_args_list] == [
        first,
        second,
    ]
    used_credentials = [call.kwargs["credential"] for call in clients.call_args_list]
    assert used_credentials[0] is not used_credentials[1]
    for credential in used_credentials:
        credential.get_token.assert_called_once_with(
            "https://search.azure.com/.default"
        )
        credential.__exit__.assert_called_once()


def test_no_rbac_permission_returns_403_without_retrying_as_backend(
    client: TestClient,
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials, clients = azure_doubles(monkeypatch)
    denied = HttpResponseError("Forbidden")
    denied.status_code = 403
    search_client = MagicMock()
    search_client.__enter__.return_value = search_client
    search_client.upload_documents.side_effect = denied
    clients.side_effect = lambda **kwargs: search_client
    response = upload(client, make_token(private_key))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "search_access_denied"
    assert credentials.call_count == 1
    search_client.__exit__.assert_called_once()


def test_obo_consent_failure_does_not_construct_search_client(
    client: TestClient,
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = MagicMock()
    credential.__enter__.return_value = credential
    credential.get_token.side_effect = ClientAuthenticationError("private diagnostic")
    factory = Mock(return_value=credential)
    clients = Mock()
    monkeypatch.setattr(resources, "OnBehalfOfCredential", factory)
    monkeypatch.setattr(resources, "SearchClient", clients)
    response = upload(client, make_token(private_key))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "delegated_authentication_failed"
    assert "private diagnostic" not in response.text
    clients.assert_not_called()
    credential.__exit__.assert_called_once()


def test_missing_auth_configuration_does_not_enable_anonymous_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = entra_settings(
        entra_tenant_id=None,
        entra_api_client_id=None,
        entra_api_client_secret=None,
        entra_frontend_client_id=None,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    with TestClient(main.create_app()) as client:
        assert upload(client, None).status_code == 401
        assert upload(client, "some-token").status_code == 503


def test_configuration_requires_complete_distinct_app_registrations() -> None:
    with pytest.raises(ValidationError):
        entra_settings(entra_api_client_secret=None)
    with pytest.raises(ValidationError):
        entra_settings(entra_frontend_client_id=API_CLIENT)
    assert "test-api-secret" not in repr(entra_settings())


def test_user_repr_does_not_contain_token(
    client: TestClient, private_key: rsa.RSAPrivateKey
) -> None:
    token = make_token(private_key)
    verifier: EntraTokenVerifier = client.app.state.token_verifier
    user = verifier.verify(token)
    assert user.object_id == USER_ID
    assert token not in repr(user)
