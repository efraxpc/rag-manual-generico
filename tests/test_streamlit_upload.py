from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import httpx
import pytest

from app import streamlit_app
from app.schemas.documents import UploadDocumentResponse


def result() -> dict:
    return {
        "document_id": "doc",
        "source": "manual.txt",
        "indexed_chunks": 2,
        "warnings": ["Página 2 omitida"],
    }


def test_sends_multipart_and_reads_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock(return_value=httpx.Response(200, json=result()))
    monkeypatch.setattr(streamlit_app.httpx, "post", post)
    response = streamlit_app.upload_document(
        " http://api/ ", "manual.txt", b"Text", access_token="user-token"
    )
    assert response.indexed_chunks == 2
    assert post.call_args.args == ("http://api/api/v1/documents/upload",)
    assert post.call_args.kwargs["files"] == {
        "file": ("manual.txt", b"Text", "application/octet-stream")
    }
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer user-token"}
    assert post.call_args.kwargs["follow_redirects"] is False


def test_401_requests_new_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        streamlit_app.httpx, "post", Mock(return_value=httpx.Response(401))
    )
    with pytest.raises(streamlit_app.SessionExpiredError):
        streamlit_app.upload_document(
            "http://api", "manual.txt", b"Text", access_token="expired"
        )


def test_empty_token_does_not_send_request(monkeypatch: pytest.MonkeyPatch) -> None:
    post = Mock()
    monkeypatch.setattr(streamlit_app.httpx, "post", post)
    with pytest.raises(streamlit_app.SessionExpiredError):
        streamlit_app.upload_document(
            "http://api", "manual.txt", b"Text", access_token=""
        )
    post.assert_not_called()


@pytest.mark.parametrize(
    "response,message",
    [
        (
            httpx.Response(
                502, json={"error": {"message": "Algunos fragmentos fallaron"}}
            ),
            "Algunos fragmentos fallaron",
        ),
        (httpx.Response(503, text="Unavailable"), "respuesta no válida"),
        (httpx.Response(200, json={}), "respuesta no válida"),
        (httpx.Response(422, json={"detail": []}), "rechazó"),
    ],
)
def test_upload_handles_api_errors(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response, message: str
) -> None:
    monkeypatch.setattr(streamlit_app.httpx, "post", Mock(return_value=response))
    with pytest.raises(streamlit_app.DocumentUploadError, match=message):
        streamlit_app.upload_document(
            "http://api", "manual.txt", b"Text", access_token="user-token"
        )


def test_upload_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        streamlit_app.httpx,
        "post",
        Mock(side_effect=httpx.ReadTimeout("private detail")),
    )
    with pytest.raises(streamlit_app.DocumentUploadError, match="reintentar"):
        streamlit_app.upload_document(
            "http://api", "manual.txt", b"Text", access_token="user-token"
        )


def test_oversized_upload_does_not_contact_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(streamlit_app, "MAX_UPLOAD_BYTES", 1)
    post = Mock()
    monkeypatch.setattr(streamlit_app.httpx, "post", post)
    with pytest.raises(streamlit_app.DocumentUploadError, match="10 MiB"):
        streamlit_app.upload_document(
            "http://api", "manual.txt", b"Text", access_token="user-token"
        )
    post.assert_not_called()


def test_button_sends_once_and_reruns_keep_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui = MagicMock()
    ui.session_state = {}
    ui.button.side_effect = [False, True, False, False]
    upload = Mock(return_value=UploadDocumentResponse(**result()))
    monkeypatch.setattr(streamlit_app, "st", ui)
    monkeypatch.setattr(streamlit_app, "upload_document", upload)
    manual = SimpleNamespace(name="manual.txt", file_id="1", getvalue=lambda: b"Text")
    streamlit_app.render_document_upload(manual, "http://api", "user-token")
    upload.assert_not_called()
    streamlit_app.render_document_upload(manual, "http://api", "user-token")
    streamlit_app.render_document_upload(manual, "http://api", "user-token")
    upload.assert_called_once_with(
        "http://api", "manual.txt", b"Text", access_token="user-token"
    )
    assert ui.session_state["upload_result"]["indexed_chunks"] == 2
    ui.warning.assert_called_with("Página 2 omitida")
    # Cambiar la API invalida el estado, sin volver a enviar el archivo.
    streamlit_app.render_document_upload(manual, "http://other-api", "user-token")
    assert "upload_result" not in ui.session_state
    assert upload.call_count == 1


def test_failed_retry_removes_previous_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ui = MagicMock()
    ui.session_state = {}
    ui.button.return_value = True
    upload = Mock(
        side_effect=[
            UploadDocumentResponse(**result()),
            streamlit_app.DocumentUploadError("Error de Azure"),
        ]
    )
    monkeypatch.setattr(streamlit_app, "st", ui)
    monkeypatch.setattr(streamlit_app, "upload_document", upload)
    manual = SimpleNamespace(name="manual.txt", file_id="1", getvalue=lambda: b"Text")
    streamlit_app.render_document_upload(manual, "http://api", "user-token")
    streamlit_app.render_document_upload(manual, "http://api", "user-token")
    assert "upload_result" not in ui.session_state
    ui.error.assert_called_with("Error de Azure")
    assert ui.success.call_count == 1
