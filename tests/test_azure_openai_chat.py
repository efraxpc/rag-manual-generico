import json
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError

from app.integrations.azure_openai_chat import (
    AZURE_AI_SCOPE,
    AzureOpenAIChatClient,
    RagProviderError,
)


def make_client(
    handler: Any, credential: Mock | None = None
) -> tuple[AzureOpenAIChatClient, httpx.Client, Mock]:
    credential = credential or Mock()
    credential.get_token.return_value = AccessToken("test-token", 4_102_444_800)
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        AzureOpenAIChatClient(
            endpoint="https://example.openai.azure.com/",
            deployment="candidate-deployment",
            credential=credential,
            http_client=http_client,
        ),
        http_client,
        credential,
    )


def test_generates_answer_with_entra_token() -> None:
    recorded: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["request"] = request
        recorded["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "  Respuesta citada.  "}}]},
        )

    client, http_client, credential = make_client(handler)
    with http_client:
        result = client.complete(system_prompt="system", user_prompt="user")

    request = recorded["request"]
    body = recorded["body"]
    assert request.url == (
        "https://example.openai.azure.com/openai/v1/chat/completions"
    )
    assert request.headers["Authorization"] == "Bearer test-token"
    assert body["model"] == "candidate-deployment"
    assert body["messages"][0] == {"role": "system", "content": "system"}
    assert result == "Respuesta citada."
    credential.get_token.assert_called_once_with(AZURE_AI_SCOPE)


def test_hides_provider_body_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "sensitive body"}})

    client, http_client, _ = make_client(handler)
    with http_client, pytest.raises(RagProviderError, match="HTTP 429") as error:
        client.complete(system_prompt="system", user_prompt="user")

    assert "sensitive" not in str(error.value)


@pytest.mark.parametrize(
    "message",
    [
        {"content": ""},
        {"refusal": "No puedo responder", "content": None},
    ],
)
def test_rejects_unusable_model_response(message: dict[str, object]) -> None:
    client, http_client, _ = make_client(
        lambda request: httpx.Response(200, json={"choices": [{"message": message}]})
    )
    with http_client, pytest.raises(RagProviderError):
        client.complete(system_prompt="system", user_prompt="user")


def test_exposes_authentication_failure_as_provider_error() -> None:
    credential = Mock()
    credential.get_token.side_effect = ClientAuthenticationError("denied")
    client, http_client, _ = make_client(
        lambda request: httpx.Response(200), credential=credential
    )

    with http_client, pytest.raises(RagProviderError, match="token"):
        client.complete(system_prompt="system", user_prompt="user")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.openai.azure.com",
        "https://example.openai.azure.com/openai/v1",
        "https://example.openai.azure.com?api-version=preview",
    ],
)
def test_rejects_endpoint_that_could_misroute_token(endpoint: str) -> None:
    with httpx.Client() as http_client, pytest.raises(ValueError, match="HTTPS"):
        AzureOpenAIChatClient(
            endpoint=endpoint,
            deployment="candidate",
            credential=Mock(),
            http_client=http_client,
        )
