"""Generar respuestas RAG candidatas para un dataset de evaluación."""

import argparse
import json
import sys
import time
from collections.abc import Mapping
from pathlib import Path

import httpx
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.evaluation.models import (
    EvaluationCase,
    EvaluationContext,
    EvaluationScenario,
)
from app.integrations.azure_openai_chat import AzureOpenAIChatClient
from app.integrations.azure_text_search import AzureTextSearchAdapter
from app.rag.contracts import TextChunkStore
from app.rag.models import TextQuery
from app.services.answer import AnswerService
from app.services.file_ingestion import SUPPORTED_EXTENSIONS, FileIngestionService


class ScenarioDatasetError(ValueError):
    """El dataset de escenarios no puede ejecutarse de forma segura."""


def load_scenarios(path: Path) -> list[EvaluationScenario]:
    scenarios: list[EvaluationScenario] = []
    seen_ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ScenarioDatasetError(f"No se pudo leer el dataset: {path}.") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw_scenario = json.loads(line)
            scenario = EvaluationScenario.model_validate(raw_scenario)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ScenarioDatasetError(
                f"Escenario inválido en la línea {line_number} del dataset."
            ) from exc
        if scenario.id in seen_ids:
            raise ScenarioDatasetError(
                f"El id '{scenario.id}' está duplicado en la línea {line_number}."
            )
        seen_ids.add(scenario.id)
        scenarios.append(scenario)

    if not scenarios:
        raise ScenarioDatasetError("El dataset no contiene escenarios de evaluación.")
    return scenarios


def generate_cases(
    scenarios: list[EvaluationScenario],
    service: AnswerService,
    *,
    document_ids: Mapping[str, str] | None = None,
) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for scenario in scenarios:
        document_id = scenario.document_id
        if scenario.document_source is not None:
            if document_ids is None or scenario.document_source not in document_ids:
                raise ScenarioDatasetError(
                    f"El documento '{scenario.document_source}' del escenario "
                    f"'{scenario.id}' no fue sembrado."
                )
            document_id = document_ids[scenario.document_source]
        result = service.answer(
            TextQuery(
                question=scenario.question,
                document_id=document_id,
                top_k=scenario.top_k,
            )
        )
        try:
            case = EvaluationCase(
                id=scenario.id,
                question=scenario.question,
                answer=result.answer,
                context=[
                    EvaluationContext(
                        content=hit.content,
                        source=hit.source,
                        page=hit.page,
                    )
                    for hit in result.context
                ],
                expected_answer=scenario.expected_answer,
                expected_sources=scenario.expected_sources,
            )
        except ValidationError as exc:
            raise ScenarioDatasetError(
                f"La respuesta generada para '{scenario.id}' supera el contrato "
                "de evaluación."
            ) from exc
        cases.append(case)
    return cases


def wait_for_documents(
    client: SearchClient,
    expected_chunks: Mapping[str, int],
    *,
    timeout_seconds: float = 60,
) -> None:
    """Esperar visibilidad del corpus antes de medir la recuperación candidata."""
    pending = dict(expected_chunks)
    deadline = time.monotonic() + timeout_seconds
    while pending:
        for document_id, count in list(pending.items()):
            escaped_id = document_id.replace("'", "''")
            try:
                results = client.search(
                    search_text="*",
                    filter=f"document_id eq '{escaped_id}'",
                    select=["id"],
                )
                visible = len({result["id"] for result in results})
            except AzureError as exc:
                raise ScenarioDatasetError(
                    "No se pudo comprobar la disponibilidad del corpus en Search."
                ) from exc
            if visible >= count:
                del pending[document_id]
        if not pending:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ScenarioDatasetError(
                "El corpus no está completamente disponible en Search "
                f"tras {timeout_seconds:g} segundos; documentos pendientes: "
                f"{len(pending)}."
            )
        time.sleep(min(2, remaining))


def seed_documents(
    path: Path,
    store: TextChunkStore,
    *,
    search_client: SearchClient | None = None,
) -> dict[str, str]:
    try:
        documents = sorted(
            candidate
            for candidate in path.iterdir()
            if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    except OSError as exc:
        raise ScenarioDatasetError(
            f"No se pudo leer el directorio de documentos: {path}."
        ) from exc
    if not documents:
        raise ScenarioDatasetError(
            "El directorio de documentos no contiene archivos PDF, TXT o Markdown."
        )

    ingestion = FileIngestionService(store)
    document_ids: dict[str, str] = {}
    expected_chunks: dict[str, int] = {}
    for document in documents:
        try:
            with document.open("rb") as file:
                result = ingestion.ingest(document.name, file)
        except OSError as exc:
            raise ScenarioDatasetError(
                f"No se pudo leer el documento de evaluación: {document.name}."
            ) from exc
        document_ids[result.source] = result.document_id
        expected_chunks[result.document_id] = result.indexed_chunks
    if search_client is not None:
        wait_for_documents(search_client, expected_chunks)
    return document_ids


def write_cases(cases: list[EvaluationCase], output: Path) -> None:
    serialized = "\n".join(case.model_dump_json() for case in cases)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{serialized}\n", encoding="utf-8")
    except OSError as exc:
        raise ScenarioDatasetError(
            f"No se pudo escribir el dataset generado: {output}."
        ) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenarios", type=Path, help="Dataset JSONL de preguntas y expectativas."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Dataset JSONL de respuestas que consumirá el juez.",
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        help="Corpus versionado que se indexará antes de generar las respuestas.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = get_settings()
        scenarios = load_scenarios(args.scenarios)
    except ScenarioDatasetError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValidationError:
        print("Configuración APP_* inválida.", file=sys.stderr)
        return 2

    required = (
        settings.azure_search_endpoint,
        settings.azure_search_text_index_name,
        settings.azure_openai_endpoint,
        settings.azure_openai_chat_deployment,
    )
    if not all(required):
        print(
            "Configura el índice textual y el despliegue generador de Azure OpenAI.",
            file=sys.stderr,
        )
        return 2

    try:
        with (
            DefaultAzureCredential(
                managed_identity_client_id=settings.azure_managed_identity_client_id
            ) as credential,
            SearchClient(
                endpoint=str(settings.azure_search_endpoint),
                index_name=settings.azure_search_text_index_name,
                credential=credential,
            ) as search_client,
            httpx.Client(
                timeout=settings.rag_generation_timeout_seconds
            ) as http_client,
        ):
            store = AzureTextSearchAdapter(search_client)
            service = AnswerService(
                store,
                AzureOpenAIChatClient(
                    endpoint=str(settings.azure_openai_endpoint),
                    deployment=settings.azure_openai_chat_deployment,
                    credential=credential,
                    http_client=http_client,
                ),
            )
            document_ids = (
                seed_documents(args.documents_dir, store, search_client=search_client)
                if args.documents_dir is not None
                else None
            )
            cases = generate_cases(
                scenarios,
                service,
                document_ids=document_ids,
            )
        write_cases(cases, args.output)
    except (ApplicationError, ScenarioDatasetError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
