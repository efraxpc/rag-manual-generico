import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.commands import evaluate_answers as command
from app.commands.evaluate_answers import DatasetError, build_report, load_cases
from app.core.config import Settings
from app.evaluation.models import (
    MAX_CONTEXT_CHARACTERS,
    CaseEvaluation,
    EvaluationCase,
    JudgeAssessment,
)


def valid_case(case_id: str = "case-1") -> dict[str, object]:
    return {
        "id": case_id,
        "question": "¿Qué indica el manual?",
        "answer": "Desconectar [manual.pdf, p. 1].",
        "context": [
            {
                "content": "Desconecta el equipo.",
                "source": "manual.pdf",
                "page": 1,
            }
        ],
    }


def evaluation(case_id: str, *, passed: bool, score: int) -> CaseEvaluation:
    metric = {"score": score, "reason": "Razón comprobable."}
    return CaseEvaluation(
        case_id=case_id,
        passed=passed,
        assessment=JudgeAssessment(
            groundedness=metric,
            relevance=metric,
            completeness=metric,
            citation_quality=metric,
            unsupported_claims=[],
            missing_information=[],
        ),
    )


def test_loads_jsonl_and_ignores_blank_lines(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        f"{json.dumps(valid_case())}\n\n{json.dumps(valid_case('case-2'))}\n",
        encoding="utf-8",
    )

    cases = load_cases(dataset)

    assert [case.id for case in cases] == ["case-1", "case-2"]


def test_reports_line_for_invalid_case(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(f"{json.dumps(valid_case())}\n{{not-json}}\n", encoding="utf-8")

    with pytest.raises(DatasetError, match="línea 2"):
        load_cases(dataset)


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    line = json.dumps(valid_case())
    dataset.write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(DatasetError, match="duplicado.*línea 2"):
        load_cases(dataset)


def test_builds_aggregate_report_without_copying_case_data() -> None:
    report = build_report(
        [
            evaluation("case-1", passed=True, score=5),
            evaluation("case-2", passed=False, score=3),
        ],
        judge_deployment="judge-v1",
        threshold=4,
    )

    assert report.summary.total == 2
    assert report.summary.passed == 1
    assert report.summary.failed == 1
    assert report.summary.pass_rate == 0.5
    assert report.summary.average_scores["groundedness"] == 4.0
    serialized = report.model_dump_json()
    assert "question" not in serialized
    assert "answer" not in serialized
    assert "context" not in serialized


def test_case_limits_bound_data_sent_to_the_judge() -> None:
    case = valid_case()
    case["context"] = [
        {"content": "texto", "source": f"source-{index}"} for index in range(21)
    ]

    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(case)


def test_rejects_excessive_aggregate_context() -> None:
    case = valid_case()
    case["context"] = [
        {
            "content": "x" * 12_000,
            "source": f"source-{index}",
        }
        for index in range(MAX_CONTEXT_CHARACTERS // 12_000 + 1)
    ]

    with pytest.raises(ValidationError, match="contexto no puede superar"):
        EvaluationCase.model_validate(case)


def test_main_returns_configuration_error_before_opening_azure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(f"{json.dumps(valid_case())}\n", encoding="utf-8")
    monkeypatch.setattr(command, "get_settings", lambda: Settings(_env_file=None))
    credential_factory = Mock()
    monkeypatch.setattr(command, "DefaultAzureCredential", credential_factory)

    assert command.main([str(dataset)]) == 2
    assert "APP_AZURE_OPENAI_ENDPOINT" in capsys.readouterr().err
    credential_factory.assert_not_called()


class FakeContext:
    def __enter__(self) -> "FakeContext":
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.mark.parametrize("passed,expected_exit", [(True, 0), (False, 1)])
def test_main_uses_report_as_ci_quality_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    passed: bool,
    expected_exit: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dataset = tmp_path / "cases.jsonl"
    output = tmp_path / "report.json"
    dataset.write_text(f"{json.dumps(valid_case())}\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_judge_deployment="judge-v1",
    )
    monkeypatch.setattr(command, "get_settings", lambda: settings)
    monkeypatch.setattr(
        command, "DefaultAzureCredential", lambda **kwargs: FakeContext()
    )
    monkeypatch.setattr(command.httpx, "Client", lambda **kwargs: FakeContext())
    monkeypatch.setattr(command, "AzureOpenAIJudgeClient", lambda **kwargs: object())

    class FakeJudge:
        def __init__(self, client: object, *, threshold: int) -> None:
            pass

        def evaluate(self, case: EvaluationCase) -> CaseEvaluation:
            return evaluation(case.id, passed=passed, score=5 if passed else 3)

    monkeypatch.setattr(command, "LlmJudge", FakeJudge)

    exit_code = command.main([str(dataset), "--output", str(output)])

    assert exit_code == expected_exit
    log = capsys.readouterr().err
    assert f"Quality gate: {int(passed)}/1 casos aprobados" in log
    if not passed:
        assert "Caso rechazado case-1" in log
        assert "groundedness=3/5" in log
    assert "Razón comprobable" not in log
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["failed"] == (
        0 if passed else 1
    )
