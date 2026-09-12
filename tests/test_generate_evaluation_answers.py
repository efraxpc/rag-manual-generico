import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError

from app.commands import generate_evaluation_answers as command
from app.commands.generate_evaluation_answers import (
    ScenarioDatasetError,
    generate_cases,
    load_scenarios,
    seed_documents,
    write_cases,
)
from app.core.config import Settings
from app.evaluation.models import EvaluationScenario
from app.rag.models import RagAnswer, SearchHit


def scenario(case_id: str = "case-1") -> dict[str, object]:
    return {
        "id": case_id,
        "question": "¿Qué indica el manual?",
        "expected_answer": "Desconectar el equipo.",
        "expected_sources": ["manual.pdf, p. 1"],
        "top_k": 3,
    }


def answer() -> RagAnswer:
    return RagAnswer(
        answer="Desconectar [manual.pdf, p. 1].",
        context=[
            SearchHit(
                id="chunk-1",
                document_id="manual-1",
                content="Desconecta el equipo.",
                source="manual.pdf",
                page=1,
                score=0.9,
            )
        ],
    )


def test_loads_scenarios_and_rejects_duplicate_ids(tmp_path: Path) -> None:
    valid = tmp_path / "valid.jsonl"
    valid.write_text(json.dumps(scenario()) + "\n", encoding="utf-8")
    assert load_scenarios(valid)[0].top_k == 3

    duplicated = tmp_path / "duplicated.jsonl"
    line = json.dumps(scenario())
    duplicated.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(ScenarioDatasetError, match="duplicado.*línea 2"):
        load_scenarios(duplicated)


def test_generates_judge_cases_from_candidate_results(tmp_path: Path) -> None:
    service = Mock()
    service.answer.return_value = answer()
    scenarios = [EvaluationScenario.model_validate(scenario())]

    cases = generate_cases(scenarios, service)
    output = tmp_path / "candidate.jsonl"
    write_cases(cases, output)

    generated = json.loads(output.read_text(encoding="utf-8"))
    assert generated["id"] == "case-1"
    assert generated["question"] == "¿Qué indica el manual?"
    assert generated["answer"] == "Desconectar [manual.pdf, p. 1]."
    assert generated["context"][0]["source"] == "manual.pdf"
    assert generated["expected_answer"] == "Desconectar el equipo."
    query = service.answer.call_args.args[0]
    assert query.question == "¿Qué indica el manual?"
    assert query.top_k == 3


def test_uses_seeded_document_id_for_retrieval() -> None:
    service = Mock()
    service.answer.return_value = answer()
    source = scenario() | {"document_source": "manual.pdf"}

    generate_cases(
        [EvaluationScenario.model_validate(source)],
        service,
        document_ids={"manual.pdf": "generated-document-id"},
    )

    query = service.answer.call_args.args[0]
    assert query.document_id == "generated-document-id"


def test_rejects_scenario_whose_document_was_not_seeded() -> None:
    source = scenario() | {"document_source": "missing.pdf"}
    with pytest.raises(ScenarioDatasetError, match="no fue sembrado"):
        generate_cases(
            [EvaluationScenario.model_validate(source)],
            Mock(),
            document_ids={},
        )


def test_seeds_versioned_documents_and_returns_their_ids(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manual.md").write_text("Texto del manual.", encoding="utf-8")
    store = Mock()

    document_ids = seed_documents(corpus, store)

    assert set(document_ids) == {"manual.md"}
    assert len(document_ids["manual.md"]) == 64
    indexed = store.index_chunks.call_args.args[0]
    assert indexed[0].source == "manual.md"


def test_preserves_empty_context_as_quality_signal() -> None:
    service = Mock()
    service.answer.return_value = RagAnswer(
        answer="No encontré información suficiente.", context=[]
    )

    case = generate_cases([EvaluationScenario.model_validate(scenario())], service)[0]

    assert case.context == []


def test_waits_for_all_chunks_before_finishing_corpus_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "manual.md").write_text("Texto del manual.", encoding="utf-8")
    client = Mock()
    client.search.side_effect = [[], [{"id": "chunk-1"}]]
    sleep = Mock()
    monkeypatch.setattr(command.time, "sleep", sleep)

    ids = seed_documents(tmp_path, Mock(), search_client=client)

    assert client.search.call_count == 2
    assert client.search.call_args.kwargs["filter"] == (
        f"document_id eq '{ids['manual.md']}'"
    )
    assert client.search.call_args.kwargs["search_text"] == "*"
    sleep.assert_called_once()


def test_waits_for_partial_document_and_does_not_recheck_ready_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.search.side_effect = [
        [{"id": "a1"}],
        [{"id": "b1"}],
        [{"id": "a1"}, {"id": "a2"}],
    ]
    monkeypatch.setattr(command.time, "sleep", Mock())

    command.wait_for_documents(client, {"a": 2, "b": 1})

    assert [call.kwargs["filter"] for call in client.search.call_args_list] == [
        "document_id eq 'a'",
        "document_id eq 'b'",
        "document_id eq 'a'",
    ]


def test_visibility_timeout_fails_instead_of_evaluating_empty_context() -> None:
    client = Mock()
    client.search.return_value = []

    with pytest.raises(ScenarioDatasetError, match="documentos pendientes: 1"):
        command.wait_for_documents(client, {"manual": 1}, timeout_seconds=0)


def test_visibility_check_reports_search_failure() -> None:
    client = Mock()
    client.search.side_effect = HttpResponseError("Forbidden", status_code=403)

    with pytest.raises(ScenarioDatasetError, match="disponibilidad del corpus"):
        command.wait_for_documents(client, {"manual": 1})


def test_main_rejects_missing_candidate_configuration_before_azure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "scenarios.jsonl"
    source.write_text(json.dumps(scenario()) + "\n", encoding="utf-8")
    monkeypatch.setattr(command, "get_settings", lambda: Settings(_env_file=None))
    credential_factory = Mock()
    monkeypatch.setattr(command, "DefaultAzureCredential", credential_factory)

    exit_code = command.main(
        [str(source), "--output", str(tmp_path / "generated.jsonl")]
    )

    assert exit_code == 2
    assert "índice textual" in capsys.readouterr().err
    credential_factory.assert_not_called()


class FakeContext:
    def __enter__(self) -> "FakeContext":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_main_generates_dataset_with_candidate_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "scenarios.jsonl"
    output = tmp_path / "generated.jsonl"
    source.write_text(json.dumps(scenario()) + "\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        azure_search_endpoint="https://example.search.windows.net",
        azure_search_text_index_name="text-chunks",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="candidate-v1",
    )
    monkeypatch.setattr(command, "get_settings", lambda: settings)
    monkeypatch.setattr(
        command, "DefaultAzureCredential", lambda **kwargs: FakeContext()
    )
    monkeypatch.setattr(command, "SearchClient", lambda **kwargs: FakeContext())
    monkeypatch.setattr(command.httpx, "Client", lambda **kwargs: FakeContext())
    monkeypatch.setattr(command, "AzureTextSearchAdapter", lambda client: object())
    monkeypatch.setattr(command, "AzureOpenAIChatClient", lambda **kwargs: object())

    class FakeAnswerService:
        def __init__(self, store: object, client: object) -> None:
            pass

        def answer(self, query: object) -> RagAnswer:
            return answer()

    monkeypatch.setattr(command, "AnswerService", FakeAnswerService)

    assert command.main([str(source), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["id"] == "case-1"
