import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_judge_configuration_loads_together() -> None:
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_judge_deployment="judge-v1",
        llm_judge_timeout_seconds=30,
    )

    assert str(settings.azure_openai_endpoint) == ("https://example.openai.azure.com/")
    assert settings.azure_openai_judge_deployment == "judge-v1"
    assert settings.llm_judge_timeout_seconds == 30


def test_candidate_generation_configuration_can_load_without_judge() -> None:
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="candidate-v1",
        rag_generation_timeout_seconds=45,
    )

    assert settings.azure_openai_chat_deployment == "candidate-v1"
    assert settings.azure_openai_judge_deployment is None
    assert settings.rag_generation_timeout_seconds == 45


def test_candidate_deployment_without_endpoint_is_rejected() -> None:
    with pytest.raises(ValidationError, match="conjuntamente"):
        Settings(
            _env_file=None,
            azure_openai_chat_deployment="candidate-v1",
        )


@pytest.mark.parametrize(
    "values",
    [
        {"azure_openai_endpoint": "https://example.openai.azure.com"},
        {"azure_openai_judge_deployment": "judge-v1"},
    ],
)
def test_partial_judge_configuration_is_rejected(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="conjuntamente"):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.openai.azure.com",
        "https://example.openai.azure.com/openai/v1",
        "https://example.openai.azure.com?api-version=preview",
    ],
)
def test_insecure_or_non_root_judge_endpoint_is_rejected(endpoint: str) -> None:
    with pytest.raises(ValidationError, match="URL HTTPS"):
        Settings(
            _env_file=None,
            azure_openai_endpoint=endpoint,
            azure_openai_judge_deployment="judge-v1",
        )
