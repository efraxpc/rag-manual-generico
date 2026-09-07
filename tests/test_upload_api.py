from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api.dependencies import get_text_store
from app.core.config import Settings
from app.core.exceptions import ChunkIndexingError, TextStoreUnavailableError
from app.services.file_ingestion import MAX_UPLOAD_BYTES
from tests.pdf_factory import make_pdf


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


@pytest.mark.parametrize(
    "filename,data",
    [
        ("manual.txt", "Información".encode()),
        ("manual.md", b"# Manual"),
        ("manual.pdf", make_pdf("Manual", "")),
    ],
)
def test_upload_returns_indexed_document(
    client: TestClient, filename: str, data: bytes
) -> None:
    store = Mock()
    client.app.dependency_overrides[get_text_store] = lambda: store
    response = client.post("/api/v1/documents/upload", files={"file": (filename, data)})
    assert response.status_code == 200
    payload = response.json()
    assert payload["indexed_chunks"] == 1
    assert payload["source"] == filename
    assert len(payload["document_id"]) == 64
    assert len(payload["warnings"]) == (1 if filename.endswith(".pdf") else 0)
    assert "embedding" not in store.index_chunks.call_args.args[0][0].model_dump()


@pytest.mark.parametrize(
    "filename,data,status",
    [
        ("a.txt", b"", 422),
        ("a.pdf", b"bad", 422),
        ("a.exe", b"a", 415),
        ("a.txt", b"a" * (MAX_UPLOAD_BYTES + 1), 413),
    ],
)
def test_upload_errors(
    client: TestClient, filename: str, data: bytes, status: int
) -> None:
    response = client.post("/api/v1/documents/upload", files={"file": (filename, data)})
    assert response.status_code == status
    assert "error" in response.json()


def test_missing_file(client: TestClient) -> None:
    assert client.post("/api/v1/documents/upload").status_code == 422


def test_unconfigured_upload(client: TestClient) -> None:
    client.app.dependency_overrides.clear()
    response = client.post(
        "/api/v1/documents/upload", files={"file": ("a.txt", b"Text")}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "text_store_not_configured"
    assert client.get("/api/v1/health").status_code == 200


@pytest.mark.parametrize(
    "failure",
    [
        TextStoreUnavailableError(),
        ChunkIndexingError([{"document_id": "doc", "chunk_id": "chunk"}]),
    ],
)
def test_indexing_failure_is_not_reported_as_success(
    client: TestClient, failure: Exception
) -> None:
    store = Mock()
    store.index_chunks.side_effect = failure
    client.app.dependency_overrides[get_text_store] = lambda: store
    response = client.post(
        "/api/v1/documents/upload", files={"file": ("a.txt", b"Text")}
    )
    assert response.status_code in {502, 503}
    assert "indexed_chunks" not in response.json()
