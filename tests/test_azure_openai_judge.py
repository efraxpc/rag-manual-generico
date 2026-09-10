import json
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError

from app.integrations.azure_openai_judge import (
    AZURE_AI_SCOPE,
    AzureOpenAIJudgeClient,
    JudgeProviderError,
)


def make_client(
    handler: Any, credential: Mock | None = None
) -> tuple[AzureOpenAIJudgeClient, httpx.Client, Mock]:
    credential = credential or Mock()
    credential.get_token.return_value = AccessToken("test-token", 4_102_444_800)
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        AzureOpenAIJudgeClient(
            endpoint="https://example.openai.azure.com/",
            deployment="judge-deployment",
            credential=credential,
            http_client=http_client,
        ),
        http_client,
        credential,
    )


def test_sends_structured_request_with_entra_token() -> None:
    recorded: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["request"] = request
        recorded["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"score": 5}'}}]},
        )

    client, http_client, credential = make_client(handler)
    with http_client:
        result = client.complete_json(
            system_prompt="system",
            user_prompt="user",
            response_schema={
                "type": "object",
                "properties": {
                    "score": {"type": "integer", "minimum": 1, "maximum": 5},
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": ["score", "reason"],
                "additionalProperties": False,
            },
        )

    request = recorded["request"]
    body = recorded["body"]
    assert request.url == (
        "https://example.openai.azure.com/openai/v1/chat/completions"
    )
    assert request.headers["Authorization"] == "Bearer test-token"
    assert body["model"] == "judge-deployment"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    sent_schema = body["response_format"]["json_schema"]["schema"]
    assert sent_schema["additionalProperties"] is False
    assert "minimum" not in sent_schema["properties"]["score"]
    assert "maximum" not in sent_schema["properties"]["score"]
    assert "minLength" not in sent_schema["properties"]["reason"]
    assert result == {"score": 5}
    credential.get_token.assert_called_once_with(AZURE_AI_SCOPE)


def test_hides_provider_response_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "sensitive body"}})

    client, http_client, _ = make_client(handler)
    with http_client, pytest.raises(JudgeProviderError, match="HTTP 429") as error:
        client.complete_json(
            system_prompt="system",
            user_prompt="user",
            response_schema={"type": "object"},
        )

    assert "sensitive" not in str(error.value)


def test_rejects_non_json_model_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not-json"}}]}
        )

    client, http_client, _ = make_client(handler)
    with http_client, pytest.raises(JudgeProviderError, match="incompatible"):
        client.complete_json(
            system_prompt="system",
            user_prompt="user",
            response_schema={"type": "object"},
        )


def test_exposes_authentication_failure_as_provider_error() -> None:
    credential = Mock()
    credential.get_token.side_effect = ClientAuthenticationError("denied")
    client, http_client, _ = make_client(
        lambda request: httpx.Response(200), credential=credential
    )

    with http_client, pytest.raises(JudgeProviderError, match="token"):
        client.complete_json(
            system_prompt="system",
            user_prompt="user",
            response_schema={"type": "object"},
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.openai.azure.com",
        "https://example.openai.azure.com/openai/v1",
        "https://example.openai.azure.com?api-version=preview",
    ],
)
def test_rejects_endpoint_that_could_misroute_token(endpoint: str) -> None:
    credential = Mock()
    with httpx.Client() as http_client, pytest.raises(ValueError, match="HTTPS"):
        AzureOpenAIJudgeClient(
            endpoint=endpoint,
            deployment="judge",
            credential=credential,
            http_client=http_client,
        )
