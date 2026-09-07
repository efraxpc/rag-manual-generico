from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.search.documents.indexes import SearchIndexClient

from app.commands.prepare_text_index import build_text_index, prepare_text_index


def test_creates_missing_index() -> None:
    client = Mock(spec=SearchIndexClient)
    client.get_index.side_effect = ResourceNotFoundError()
    assert "creado" in prepare_text_index(client, "rag-text-chunks")
    index = client.create_index.call_args.args[0]
    assert index.name == "rag-text-chunks"
    fields = {f.name: f for f in index.fields}
    assert fields["id"].key
    assert fields["content"].searchable
    assert fields["document_id"].filterable
    assert "embedding" not in fields
    client.create_or_update_index.assert_not_called()


def test_accepts_existing_compatible_index_without_writes() -> None:
    client = Mock(spec=SearchIndexClient)
    client.get_index.return_value = build_text_index("text")
    assert "compatible" in prepare_text_index(client, "text")
    client.create_index.assert_not_called()
    client.create_or_update_index.assert_not_called()


@pytest.mark.parametrize(
    "field,attribute,value",
    [
        ("id", "key", False),
        ("content", "searchable", False),
        ("document_id", "filterable", False),
        ("page", "type", "Edm.String"),
        ("source", "hidden", True),
    ],
)
def test_rejects_incompatible_field_without_writes(
    field: str, attribute: str, value: object
) -> None:
    client = Mock(spec=SearchIndexClient)
    index = build_text_index("text")
    setattr(next(f for f in index.fields if f.name == field), attribute, value)
    client.get_index.return_value = index
    with pytest.raises(ValueError, match="incompatible"):
        prepare_text_index(client, "text")
    client.create_index.assert_not_called()
    client.create_or_update_index.assert_not_called()


def test_missing_field_is_incompatible() -> None:
    client = Mock(spec=SearchIndexClient)
    index = build_text_index("text")
    index.fields.pop()
    client.get_index.return_value = index
    with pytest.raises(ValueError, match="page"):
        prepare_text_index(client, "text")
    client.create_index.assert_not_called()


def test_access_error_does_not_attempt_creation() -> None:
    client = Mock(spec=SearchIndexClient)
    client.get_index.side_effect = HttpResponseError("Forbidden")
    with pytest.raises(HttpResponseError):
        prepare_text_index(client, "text")
    client.create_index.assert_not_called()
