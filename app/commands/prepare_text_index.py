"""Crear o validar el índice de texto: python -m app.commands.prepare_text_index."""

import argparse
import sys

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchField,
    SearchFieldDataType,
    SearchIndex,
)
from pydantic import ValidationError

from app.core.config import get_settings


def build_text_index(name: str) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SearchField(
                name=field_name,
                type=(
                    SearchFieldDataType.Int32
                    if field_name == "page"
                    else SearchFieldDataType.String
                ),
                key=field_name == "id",
                hidden=False,
                searchable=field_name == "content",
                filterable=field_name in {"id", "document_id"},
            )
            for field_name in (
                "id",
                "chunk_id",
                "document_id",
                "content",
                "source",
                "page",
            )
        ],
    )


def validate_text_index(actual: SearchIndex, expected: SearchIndex) -> None:
    fields = {field.name: field for field in actual.fields}
    for required in expected.fields:
        field = fields.get(required.name)
        if (
            field is None
            or field.type != required.type
            or bool(field.key) != bool(required.key)
            or field.hidden
            or (required.searchable and not field.searchable)
            or (required.filterable and not field.filterable)
        ):
            raise ValueError(
                f"Índice incompatible: revisa el campo '{required.name}'. "
                "No se ha modificado; configura un índice nuevo."
            )


def prepare_text_index(client: SearchIndexClient, name: str) -> str:
    expected = build_text_index(name)
    try:
        actual = client.get_index(name)
    except ResourceNotFoundError:
        # create_index falla si otro proceso lo creó; nunca reemplaza un índice.
        client.create_index(expected)
        return "Índice de texto creado."
    validate_text_index(actual, expected)
    return "El índice de texto existente es compatible; no se ha modificado."


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        settings = get_settings()
    except ValidationError:
        print(
            "Configuración inválida; revisa las variables APP_AZURE_SEARCH_*.",
            file=sys.stderr,
        )
        return 1
    if not settings.azure_search_endpoint or not settings.azure_search_text_index_name:
        print(
            "Configura el endpoint y APP_AZURE_SEARCH_TEXT_INDEX_NAME.", file=sys.stderr
        )
        return 1
    try:
        with (
            DefaultAzureCredential(
                managed_identity_client_id=settings.azure_managed_identity_client_id
            ) as credential,
            SearchIndexClient(
                endpoint=str(settings.azure_search_endpoint), credential=credential
            ) as client,
        ):
            print(prepare_text_index(client, settings.azure_search_text_index_name))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except AzureError:
        print(
            "No se pudo preparar el índice. Revisa conexión, configuración y permisos "
            "de administración de índices en Azure AI Search.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
