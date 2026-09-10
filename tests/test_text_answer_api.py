from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api.dependencies import get_answer_service
from app.core.config import Settings
from app.integrations.azure_openai_chat import RagProviderError
from app.rag.models import RagAnswer, SearchHit


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "get_settings", lambda: Settings(_env_file=None))
    app = main.create_app()
    service = Mock()
    service.answer.return_value = RagAnswer(
        answer="Desconecta [manual.pdf, p. 1].",
        context=[
            SearchHit(
                id="chunk-1",
                document_id="manual-1",
                content="Desconecta el equipo.",
                source="manual.pdf",
                page=1,
                score=1.0,
            )
        ],
    )
    app.dependency_overrides[get_answer_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def test_answers_question_with_context(client: TestClient) -> None:
    response = client.post(
        "/api/v1/queries/answer",
        json={"question": "¿Qué debo hacer?", "document_id": "manual-1"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Desconecta [manual.pdf, p. 1]."
    assert response.json()["context"][0]["source"] == "manual.pdf"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "pregunta", "top_k": 0},
        {"question": "pregunta", "top_k": 21},
    ],
)
def test_rejects_invalid_question(
    client: TestClient, payload: dict[str, object]
) -> None:
    assert client.post("/api/v1/queries/answer", json=payload).status_code == 422


def test_exposes_generation_failure_as_controlled_error(client: TestClient) -> None:
    service = client.app.dependency_overrides[get_answer_service]()
    service.answer.side_effect = RagProviderError("No se pudo generar la respuesta.")
    client.app.dependency_overrides[get_answer_service] = lambda: service

    response = client.post(
        "/api/v1/queries/answer", json={"question": "¿Qué debo hacer?"}
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "rag_provider_error"
