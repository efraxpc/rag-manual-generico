import logging
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError
from fastapi.testclient import TestClient

from app import main
from app.api.dependencies import get_text_store
from app.core.config import Settings
from app.integrations.azure_text_search import AzureTextSearchAdapter


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        azure_search_endpoint=None,
        azure_search_index_name=None,
        azure_search_text_index_name=None,
        azure_search_vector_dimensions=None,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    app.dependency_overrides[get_text_store] = lambda: Mock()
    with TestClient(app) as client:
        yield client


def backend_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "uvicorn.error"]


def test_azure_failure_logs_original_cause_but_keeps_response_controlled(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    azure_client = Mock()
    azure_client.upload_documents.side_effect = HttpResponseError(
        "Azure diagnostic: index does not exist"
    )
    store = AzureTextSearchAdapter(azure_client)
    client.app.dependency_overrides[get_text_store] = lambda: store
    response = client.post(
        "/api/v1/documents/upload?token=private-query",
        files={"file": ("a.txt", b"private-file-content")},
        headers={"Authorization": "Bearer private-header"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "text_store_unavailable"
    assert "Azure diagnostic" not in response.text
    records = backend_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is not None
    assert (
        "POST /api/v1/documents/upload -> 503 [text_store_unavailable]" in caplog.text
    )
    assert "Azure diagnostic: index does not exist" in caplog.text
    assert "Traceback" in caplog.text
    for private_value in ("private-query", "private-file-content", "private-header"):
        assert private_value not in caplog.text


def test_application_validation_logs_warning_without_traceback(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = client.post("/api/v1/documents/upload", files={"file": ("a.txt", b"")})
    assert response.status_code == 422
    records = backend_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is None
    assert "[invalid_document]" in caplog.text


def test_request_validation_logs_location_without_input_values(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        data={"file": "private-invalid-file"},
    )
    assert response.status_code == 422
    assert "detail" in response.json()
    records = backend_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "request_validation_error" in caplog.text
    assert "body" in caplog.text and "file" in caplog.text
    assert "private-invalid-file" not in caplog.text


def test_success_does_not_log_an_error(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = client.post(
        "/api/v1/documents/upload", files={"file": ("a.txt", b"Text")}
    )
    assert response.status_code == 200
    assert backend_records(caplog) == []
