from collections.abc import Iterator, Sequence
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.api.dependencies import get_vector_store
from app.core.auth import require_user
from app.core.config import Settings
from app.core.exceptions import ChunkIndexingError, VectorStoreUnavailableError
from app.rag.models import EmbeddedChunk, SearchHit, VectorQuery
from tests.auth_helpers import authenticated_user


class MemoryVectorStore:
    """Doble de prueba que implementa el contrato sin heredar del adaptador."""

    def __init__(self) -> None:
        self.chunks: dict[tuple[str, str], EmbeddedChunk] = {}

    def index_chunks(self, chunks: Sequence[EmbeddedChunk]) -> None:
        for chunk in chunks:
            self.chunks[(chunk.document_id, chunk.id)] = chunk

    def search(self, query: VectorQuery) -> list[SearchHit]:
        return [
            SearchHit(**chunk.model_dump(exclude={"embedding"}), score=1.0)
            for chunk in self.chunks.values()
            if query.document_id is None or chunk.document_id == query.document_id
        ][: query.top_k]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        azure_search_endpoint=None,
        azure_search_index_name=None,
        azure_search_vector_dimensions=None,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    store = MemoryVectorStore()
    app.dependency_overrides[get_vector_store] = lambda: store
    with TestClient(app) as client:
        yield client


@pytest.fixture
def chunk() -> dict:
    return {
        "id": "chunk-1",
        "document_id": "manual-1",
        "content": "Desconecta el equipo antes del mantenimiento.",
        "embedding": [0.1, 0.2, 0.3],
        "source": "manual.pdf",
        "page": 1,
    }


def test_index_and_search_with_a_different_adapter(
    client: TestClient, chunk: dict
) -> None:
    response = client.post("/api/v1/documents/chunks", json={"chunks": [chunk]})
    assert response.status_code == 200
    assert response.json() == {"indexed_chunks": 1}

    response = client.post(
        "/api/v1/queries/search",
        json={"embedding": [0.1, 0.2, 0.3], "document_id": "manual-1", "top_k": 1},
    )
    assert response.status_code == 200
    match = response.json()["matches"][0]
    assert match["id"] == "chunk-1"
    assert match["source"] == "manual.pdf"
    assert match["page"] == 1
    assert "embedding" not in match


def test_reindexing_same_chunk_updates_it(client: TestClient, chunk: dict) -> None:
    client.post("/api/v1/documents/chunks", json={"chunks": [chunk]})
    chunk["content"] = "Texto actualizado"
    client.post("/api/v1/documents/chunks", json={"chunks": [chunk]})
    response = client.post(
        "/api/v1/queries/search", json={"embedding": [0.1, 0.2, 0.3]}
    )
    assert len(response.json()["matches"]) == 1
    assert response.json()["matches"][0]["content"] == "Texto actualizado"


def test_duplicate_ids_in_a_batch_are_rejected(client: TestClient, chunk: dict) -> None:
    response = client.post("/api/v1/documents/chunks", json={"chunks": [chunk, chunk]})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "duplicate_chunk_id"


@pytest.mark.parametrize(
    "changes", [{"embedding": []}, {"content": " "}, {"page": 0}, {"id": ""}]
)
def test_invalid_chunks_are_rejected(
    client: TestClient, chunk: dict, changes: dict
) -> None:
    response = client.post(
        "/api/v1/documents/chunks", json={"chunks": [chunk | changes]}
    )
    assert response.status_code == 422


def test_empty_batch_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/documents/chunks", json={"chunks": []})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"embedding": []},
        {"embedding": [0.1], "top_k": 0},
        {"embedding": [0.1], "top_k": 51},
    ],
)
def test_invalid_queries_are_rejected(client: TestClient, payload: dict) -> None:
    assert client.post("/api/v1/queries/search", json=payload).status_code == 422


def test_empty_search_is_a_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/queries/search", json={"embedding": [0.1, 0.2, 0.3]}
    )
    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_unconfigured_store_returns_503_but_health_still_works(
    client: TestClient,
) -> None:
    client.app.dependency_overrides.clear()
    client.app.dependency_overrides[require_user] = authenticated_user
    response = client.post(
        "/api/v1/queries/search", json={"embedding": [0.1, 0.2, 0.3]}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "vector_store_not_configured"
    assert client.get("/api/v1/health").status_code == 200


def test_upstream_search_error_is_exposed_as_controlled_error(
    client: TestClient,
) -> None:
    store = Mock()
    store.search.side_effect = VectorStoreUnavailableError()
    client.app.dependency_overrides[get_vector_store] = lambda: store
    response = client.post(
        "/api/v1/queries/search", json={"embedding": [0.1, 0.2, 0.3]}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "vector_store_unavailable"


def test_partial_indexing_does_not_report_success(
    client: TestClient, chunk: dict
) -> None:
    store = Mock()
    store.index_chunks.side_effect = ChunkIndexingError(
        [{"document_id": "manual-1", "chunk_id": "chunk-1"}]
    )
    client.app.dependency_overrides[get_vector_store] = lambda: store
    response = client.post("/api/v1/documents/chunks", json={"chunks": [chunk]})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "chunk_indexing_failed"
    assert "indexed_chunks" not in response.json()
