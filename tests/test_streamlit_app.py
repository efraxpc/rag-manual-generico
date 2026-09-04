import json
from io import BytesIO

import pytest

from app import streamlit_app


class FakeResponse(BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_build_health_url_normalizes_trailing_slash() -> None:
    assert (
        streamlit_app.build_health_url("http://localhost:8000/")
        == "http://localhost:8000/api/v1/health"
    )


def test_fetch_api_health_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "status": "ok",
        "service": "RAG Manual API",
        "version": "0.1.0",
    }

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        assert timeout == 2
        return FakeResponse(json.dumps(payload).encode())

    streamlit_app.fetch_api_health.clear()
    monkeypatch.setattr(streamlit_app, "urlopen", fake_urlopen)

    assert streamlit_app.fetch_api_health("http://api.example") == payload


def test_fetch_api_health_rejects_invalid_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        return FakeResponse(b'{"status": "degraded"}')

    streamlit_app.fetch_api_health.clear()
    monkeypatch.setattr(streamlit_app, "urlopen", fake_urlopen)

    with pytest.raises(streamlit_app.ApiUnavailableError):
        streamlit_app.fetch_api_health("http://api.example")
