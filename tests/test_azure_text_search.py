from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.models import IndexingResult

from app.core.exceptions import ChunkIndexingError, TextStoreUnavailableError
from app.integrations import azure_text_search
from app.integrations.azure_text_search import AzureTextSearchAdapter
from app.rag.models import Chunk


@pytest.fixture
def client() -> Mock:
    client = Mock(spec=SearchClient)
    client.upload_documents.side_effect = lambda documents: [
        IndexingResult.deserialize({"key": doc["id"], "status": True})
        for doc in documents
    ]
    return client


def chunk(number: int = 0, content: str = "Texto") -> Chunk:
    return Chunk(
        id=str(number), document_id="doc", content=content, source="manual.pdf", page=1
    )


def test_maps_text_and_reuses_keys(client: Mock) -> None:
    adapter = AzureTextSearchAdapter(client)
    adapter.index_chunks([chunk()])
    first = client.upload_documents.call_args.kwargs["documents"][0]
    adapter.index_chunks([chunk(content="Actualizado")])
    second = client.upload_documents.call_args.kwargs["documents"][0]
    assert len(first["id"]) == 64
    assert first["id"] == second["id"]
    assert first == {
        "id": first["id"],
        "chunk_id": "0",
        "document_id": "doc",
        "content": "Texto",
        "source": "manual.pdf",
        "page": 1,
    }
    assert second["content"] == "Actualizado"


def test_splits_by_document_count(client: Mock) -> None:
    AzureTextSearchAdapter(client).index_chunks([chunk(i) for i in range(1001)])
    assert [
        len(c.kwargs["documents"]) for c in client.upload_documents.call_args_list
    ] == [1000, 1]


def test_splits_by_serialized_bytes(
    client: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(azure_text_search, "INDEX_BATCH_BYTES", 14_000)
    AzureTextSearchAdapter(client).index_chunks(
        [chunk(i, "á" * 1000) for i in range(3)]
    )
    assert [
        len(c.kwargs["documents"]) for c in client.upload_documents.call_args_list
    ] == [2, 1]


@pytest.mark.parametrize("missing_result", [True, False])
def test_reports_failed_or_missing_results(client: Mock, missing_result: bool) -> None:
    def upload(documents: list[dict]) -> list[IndexingResult]:
        return [
            IndexingResult.deserialize({"key": doc["id"], "status": index == 0})
            for index, doc in enumerate(documents)
            if index == 0 or not missing_result
        ]

    client.upload_documents.side_effect = upload
    with pytest.raises(ChunkIndexingError) as error:
        AzureTextSearchAdapter(client).index_chunks([chunk(0), chunk(1)])
    assert error.value.details == {
        "failed_chunks": [{"document_id": "doc", "chunk_id": "1"}]
    }


def test_provider_failure_has_no_private_details(client: Mock) -> None:
    client.upload_documents.side_effect = HttpResponseError("private detail")
    with pytest.raises(TextStoreUnavailableError) as error:
        AzureTextSearchAdapter(client).index_chunks([chunk()])
    assert "private detail" not in str(error.value)


def test_stops_after_failed_batch(
    client: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(azure_text_search, "INDEX_BATCH_SIZE", 1)
    client.upload_documents.side_effect = HttpResponseError()
    with pytest.raises(TextStoreUnavailableError):
        AzureTextSearchAdapter(client).index_chunks([chunk(0), chunk(1)])
    assert client.upload_documents.call_count == 1
