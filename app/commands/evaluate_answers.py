"""Evaluar respuestas RAG: python -m app.commands.evaluate_answers DATASET."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential
from pydantic import ValidationError

from app.core.config import get_settings
from app.evaluation.judge import (
    METRIC_NAMES,
    RUBRIC_VERSION,
    InvalidJudgeResponseError,
    LlmJudge,
)
from app.evaluation.models import (
    CaseEvaluation,
    EvaluationCase,
    EvaluationReport,
    EvaluationSummary,
)
from app.integrations.azure_openai_judge import (
    AzureOpenAIJudgeClient,
    JudgeProviderError,
)


class DatasetError(ValueError):
    """El dataset no cumple el contrato JSONL de evaluación."""


def load_cases(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DatasetError(f"No se pudo leer el dataset: {path}.") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw_case = json.loads(line)
            case = EvaluationCase.model_validate(raw_case)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise DatasetError(
                f"Caso inválido en la línea {line_number} del dataset."
            ) from exc
        if case.id in seen_ids:
            raise DatasetError(
                f"El id '{case.id}' está duplicado en la línea {line_number}."
            )
        seen_ids.add(case.id)
        cases.append(case)

    if not cases:
        raise DatasetError("El dataset no contiene casos de evaluación.")
    return cases


def build_report(
    results: list[CaseEvaluation],
    *,
    judge_deployment: str,
    threshold: int,
) -> EvaluationReport:
    if not results:
        raise ValueError("Se necesita al menos un resultado")
    passed = sum(result.passed for result in results)
    averages = {
        name: round(
            sum(getattr(result.assessment, name).score for result in results)
            / len(results),
            2,
        )
        for name in METRIC_NAMES
    }
    return EvaluationReport(
        generated_at=datetime.now(UTC),
        rubric_version=RUBRIC_VERSION,
        judge_deployment=judge_deployment,
        threshold=threshold,
        summary=EvaluationSummary(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            pass_rate=round(passed / len(results), 4),
            average_scores=averages,
        ),
        results=results,
    )


def write_report(report: EvaluationReport, output: Path | None) -> None:
    serialized = report.model_dump_json(indent=2)
    if output is None:
        print(serialized)
        return
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{serialized}\n", encoding="utf-8")
    except OSError as exc:
        raise DatasetError(f"No se pudo escribir el reporte: {output}.") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Dataset JSONL que se evaluará.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Archivo JSON de salida; si se omite, se imprime por stdout.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        choices=range(1, 6),
        default=4,
        metavar="1..5",
        help="Puntuación mínima por métrica (por defecto: 4).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = get_settings()
        cases = load_cases(args.dataset)
    except DatasetError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValidationError:
        print("Configuración APP_* inválida.", file=sys.stderr)
        return 2

    if not settings.azure_openai_endpoint or not settings.azure_openai_judge_deployment:
        print(
            "Configura APP_AZURE_OPENAI_ENDPOINT y APP_AZURE_OPENAI_JUDGE_DEPLOYMENT.",
            file=sys.stderr,
        )
        return 2

    try:
        with (
            DefaultAzureCredential(
                managed_identity_client_id=settings.azure_managed_identity_client_id
            ) as credential,
            httpx.Client(timeout=settings.llm_judge_timeout_seconds) as http_client,
        ):
            client = AzureOpenAIJudgeClient(
                endpoint=str(settings.azure_openai_endpoint),
                deployment=settings.azure_openai_judge_deployment,
                credential=credential,
                http_client=http_client,
            )
            judge = LlmJudge(client, threshold=args.threshold)
            results = [judge.evaluate(case) for case in cases]
        report = build_report(
            results,
            judge_deployment=settings.azure_openai_judge_deployment,
            threshold=args.threshold,
        )
        write_report(report, args.output)
    except (DatasetError, InvalidJudgeResponseError, JudgeProviderError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0 if report.summary.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
