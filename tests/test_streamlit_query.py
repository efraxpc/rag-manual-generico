from unittest.mock import Mock

import httpx
import pytest

from app import streamlit_app


def response() -> dict[str, object]:
    return {
        "answer": "Desconecta [manual.pdf, p. 1].",
        "context": [
            {
                "id": "chunk-1",
                "document_id": "doc-1",
                "content": "Desconecta el equipo.",
                "source": "manual.pdf",
                "page": 1,
                "score": 1.0,
            }
        ],
    }


def test_asks_api_with_document_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock(return_value=httpx.Response(200, json=response()))
    monkeypatch.setattr(streamlit_app.httpx, "post", post)

    result = streamlit_app.ask_question(
        " http://api/ ",
        "¿Qué debo hacer?",
        access_token="user-token",
        document_id="doc-1",
    )

    assert result.answer.startswith("Desconecta")
    assert post.call_args.args == ("http://api/api/v1/queries/answer",)
    assert post.call_args.kwargs["json"] == {
        "question": "¿Qué debo hacer?",
        "document_id": "doc-1",
        "top_k": 5,
    }
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer user-token"}


def test_question_401_requests_new_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        streamlit_app.httpx, "post", Mock(return_value=httpx.Response(401))
    )
    with pytest.raises(streamlit_app.QuestionSessionExpiredError):
        streamlit_app.ask_question(
            "http://api",
            "pregunta",
            access_token="expired",
            document_id="doc-1",
        )
