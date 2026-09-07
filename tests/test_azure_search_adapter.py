from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError, ServiceRequestError
from azure.search.documents import SearchClient
from azure.search.documents.models import IndexingResult
from pydantic import ValidationError

from app.core.exceptions import (
    ApplicationError,
    ChunkIndexingError,
    VectorStoreUnavailableError,
)
from app.integrations.azure_search import AzureSearchAdapter
from app.rag.models import EmbeddedChunk, VectorQuery


@pytest.fixture
def chunk() -> EmbeddedChunk:
    return EmbeddedChunk(
        id="página 1/fragmento 0",
        document_id="manual-1",
        content="Desconecta el equipo antes del mantenimiento.",
        embedding=[0.1, 0.2, 0.3],
        source="manual.pdf",
        page=1,
    )


@pytest.fixture
def client() -> Mock:
    client = Mock(spec=SearchClient)
    client.upload_documents.side_effect = lambda documents: [
        IndexingResult.deserialize({"key": document["id"], "status": True})
        for document in documents
    ]
    return client


def test_index_chunks_translates_models_and_reuses_keys(
    client: Mock, chunk: EmbeddedChunk
) -> None:
    adapter = AzureSearchAdapter(client, vector_dimensions=3)

    adapter.index_chunks([chunk])
    first = client.upload_documents.call_args.kwargs["documents"][0]
    adapter.index_chunks(
        [chunk.model_copy(update={"content": "Contenido actualizado"})]
    )
    updated = client.upload_documents.call_args.kwargs["documents"][0]

    assert first["chunk_id"] == chunk.id
    assert first["document_id"] == chunk.document_id
    assert first["content"] == chunk.content
    assert first["source"] == chunk.source
    assert first["page"] == 1
    assert first["embedding"] == [0.1, 0.2, 0.3]
    assert len(first["id"]) == 64
    assert updated["id"] == first["id"]
    assert updated["content"] == "Contenido actualizado"

    adapter.index_chunks([chunk.model_copy(update={"document_id": "manual-2"})])
    other_document = client.upload_documents.call_args.kwargs["documents"][0]
    assert other_document["id"] != first["id"]


def test_index_chunks_splits_large_batches(client: Mock, chunk: EmbeddedChunk) -> None:
    chunks = [chunk.model_copy(update={"id": str(number)}) for number in range(1001)]
    AzureSearchAdapter(client, vector_dimensions=3).index_chunks(chunks)

    assert [
        len(call.kwargs["documents"]) for call in client.upload_documents.call_args_list
    ] == [1000, 1]


@pytest.mark.parametrize("missing_result", [False, True])
def test_partial_indexing_is_reported(
    client: Mock, chunk: EmbeddedChunk, missing_result: bool
) -> None:
    def upload(documents: list[dict]) -> list[IndexingResult]:
        results = [
            IndexingResult.deserialize({"key": documents[0]["id"], "status": True})
        ]
        if not missing_result:
            results.append(
                IndexingResult.deserialize(
                    {
                        "key": documents[1]["id"],
                        "status": False,
                        "errorMessage": "Detalle interno que no debe exponerse",
                    }
                )
            )
        return results

    client.upload_documents.side_effect = upload
    chunks = [chunk, chunk.model_copy(update={"id": "chunk-2"})]

    with pytest.raises(ChunkIndexingError) as error:
        AzureSearchAdapter(client, vector_dimensions=3).index_chunks(chunks)

    assert error.value.details == {
        "failed_chunks": [{"document_id": "manual-1", "chunk_id": "chunk-2"}]
    }
    assert "Detalle interno" not in str(error.value)


@pytest.mark.parametrize("embedding", [[1.0, 2.0], [0.0, 0.0, 0.0]])
def test_bad_embedding_is_rejected_before_any_write(
    client: Mock, chunk: EmbeddedChunk, embedding: list[float]
) -> None:
    invalid = chunk.model_copy(update={"embedding": embedding})
    with pytest.raises(ApplicationError) as error:
        AzureSearchAdapter(client, vector_dimensions=3).index_chunks([chunk, invalid])

    assert error.value.status_code == 422
    client.upload_documents.assert_not_called()


def test_search_translates_vectors_filters_and_results(client: Mock) -> None:
    client.search.return_value = [
        {
            "id": "azure-key",
            "chunk_id": "chunk-1",
            "document_id": "O'Brien",
            "content": "Texto del manual",
            "source": "manual.pdf",
            "page": 2,
            "@search.score": 0.91,
        }
    ]
    query = VectorQuery(embedding=[0.1, 0.2, 0.3], document_id="O'Brien", top_k=3)

    matches = AzureSearchAdapter(client, vector_dimensions=3).search(query)

    arguments = client.search.call_args.kwargs
    vector = arguments["vector_queries"][0]
    assert arguments["search_text"] is None
    assert vector.vector == query.embedding
    assert vector.fields == "embedding"
    assert vector.k_nearest_neighbors == 3
    assert arguments["filter"] == "document_id eq 'O''Brien'"
    assert arguments["vector_filter_mode"] == "preFilter"
    assert arguments["top"] == 3
    assert "embedding" not in arguments["select"]
    assert matches[0].model_dump() == {
        "id": "chunk-1",
        "document_id": "O'Brien",
        "content": "Texto del manual",
        "source": "manual.pdf",
        "page": 2,
        "score": 0.91,
    }


def test_search_without_matches_or_document_filter(client: Mock) -> None:
    client.search.return_value = []
    assert (
        AzureSearchAdapter(client, vector_dimensions=3).search(
            VectorQuery(embedding=[0.1, 0.2, 0.3])
        )
        == []
    )
    assert client.search.call_args.kwargs["filter"] is None


def test_search_rejects_incompatible_dimensions(client: Mock) -> None:
    with pytest.raises(ApplicationError) as error:
        AzureSearchAdapter(client, vector_dimensions=3).search(
            VectorQuery(embedding=[0.1])
        )
    assert error.value.code == "invalid_embedding_dimensions"
    client.search.assert_not_called()


def test_upload_translates_azure_failure(client: Mock, chunk: EmbeddedChunk) -> None:
    client.upload_documents.side_effect = HttpResponseError("Detalle privado de Azure")
    with pytest.raises(VectorStoreUnavailableError) as error:
        AzureSearchAdapter(client, vector_dimensions=3).index_chunks([chunk])
    assert "Detalle privado" not in str(error.value)


def test_search_translates_failure_during_pagination(client: Mock) -> None:
    def results() -> Iterator[dict]:
        raise ServiceRequestError("Conexión interrumpida")
        yield {}  # pragma: no cover

    client.search.return_value = results()
    with pytest.raises(VectorStoreUnavailableError):
        AzureSearchAdapter(client, vector_dimensions=3).search(
            VectorQuery(embedding=[0.1, 0.2, 0.3])
        )


def test_search_rejects_incompatible_index_fields(client: Mock) -> None:
    client.search.return_value = [{"id": "missing-fields"}]
    with pytest.raises(ApplicationError) as error:
        AzureSearchAdapter(client, vector_dimensions=3).search(
            VectorQuery(embedding=[0.1, 0.2, 0.3])
        )
    assert error.value.code == "invalid_vector_store_response"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_query_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        VectorQuery(embedding=[value])
