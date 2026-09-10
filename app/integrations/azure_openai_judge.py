"""Cliente mínimo para ejecutar el juez con Azure OpenAI y Entra ID."""

import json
from collections.abc import Mapping
from typing import Any

import httpx
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError

AZURE_AI_SCOPE = "https://ai.azure.com/.default"
UNSUPPORTED_STRUCTURED_OUTPUT_KEYWORDS = frozenset(
    {
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "multipleOf",
        "patternProperties",
        "unevaluatedProperties",
        "propertyNames",
        "minProperties",
        "maxProperties",
        "unevaluatedItems",
        "contains",
        "minContains",
        "maxContains",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
)


class JudgeProviderError(RuntimeError):
    """Azure OpenAI no pudo producir una evaluación utilizable."""


def azure_compatible_schema(value: Any) -> Any:
    """Retira restricciones no admitidas por Structured Outputs de Azure."""
    if isinstance(value, Mapping):
        compatible: dict[str, Any] = {}
        for key, child in value.items():
            if key in UNSUPPORTED_STRUCTURED_OUTPUT_KEYWORDS:
                continue
            if key == "properties" and isinstance(child, Mapping):
                compatible[key] = {
                    property_name: azure_compatible_schema(property_schema)
                    for property_name, property_schema in child.items()
                }
            else:
                compatible[key] = azure_compatible_schema(child)
        return compatible
    if isinstance(value, list):
        return [azure_compatible_schema(child) for child in value]
    return value


class AzureOpenAIJudgeClient:
    def __init__(
        self,
        *,
        endpoint: str,
        deployment: str,
        credential: TokenCredential,
        http_client: httpx.Client,
    ) -> None:
        base_url = httpx.URL(endpoint)
        if (
            base_url.scheme != "https"
            or not base_url.host
            or base_url.path not in {"", "/"}
            or base_url.query
            or base_url.fragment
        ):
            raise ValueError(
                "endpoint debe ser una URL HTTPS de recurso, sin ruta ni query"
            )
        if not deployment.strip():
            raise ValueError("deployment no puede estar vacío")
        self._url = f"{str(base_url).rstrip('/')}/openai/v1/chat/completions"
        self._deployment = deployment
        self._credential = credential
        self._http_client = http_client

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            token = self._credential.get_token(AZURE_AI_SCOPE).token
        except AzureError as exc:
            raise JudgeProviderError(
                "No se pudo obtener un token de Entra ID para Azure OpenAI."
            ) from exc

        try:
            response = self._http_client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._deployment,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_completion_tokens": 2_000,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "rag_judgment",
                            "strict": True,
                            # Pydantic conserva los límites para validar localmente,
                            # pero Azure solo acepta un subconjunto de JSON Schema.
                            "schema": azure_compatible_schema(response_schema),
                        },
                    },
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            status = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            suffix = f" (HTTP {status})" if status is not None else ""
            raise JudgeProviderError(
                f"Azure OpenAI no pudo ejecutar el juez{suffix}."
            ) from exc

        try:
            payload = response.json()
            message = payload["choices"][0]["message"]
            if message.get("refusal"):
                raise JudgeProviderError("El modelo juez rechazó evaluar el caso.")
            content = message["content"]
            parsed = json.loads(content)
        except JudgeProviderError:
            raise
        except (json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
            raise JudgeProviderError(
                "Azure OpenAI devolvió una respuesta incompatible para el juez."
            ) from exc

        if not isinstance(parsed, dict):
            raise JudgeProviderError(
                "Azure OpenAI devolvió una respuesta incompatible para el juez."
            )
        return parsed
