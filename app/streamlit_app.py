"""Interfaz web básica para RAG Manual."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx
import streamlit as st
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.documents import UploadDocumentResponse
from app.services.file_ingestion import MAX_UPLOAD_BYTES

SUPPORTED_FILE_TYPES = ["pdf", "txt", "md"]


class ApiUnavailableError(RuntimeError):
    """Indica que la interfaz no pudo consultar el estado de la API."""


class DocumentUploadError(RuntimeError):
    """Error de carga que se puede mostrar en la interfaz."""


def upload_document(api_url: str, filename: str, data: bytes) -> UploadDocumentResponse:
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentUploadError("El archivo supera el límite de 10 MiB.")
    url = f"{api_url.strip().rstrip('/')}/api/v1/documents/upload"
    try:
        response = httpx.post(
            url,
            files={"file": (filename, data, "application/octet-stream")},
            timeout=httpx.Timeout(120, connect=5),
        )
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise DocumentUploadError(
            "No se pudo completar la carga. Puedes reintentar con el mismo archivo."
        ) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise DocumentUploadError("La API devolvió una respuesta no válida.") from exc
    if response.is_error:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message") if isinstance(error, dict) else None
        raise DocumentUploadError(
            message if isinstance(message, str) else "La API rechazó el archivo."
        )
    try:
        return UploadDocumentResponse.model_validate(payload)
    except ValidationError as exc:
        raise DocumentUploadError("La API devolvió una respuesta no válida.") from exc


def build_health_url(api_url: str) -> str:
    """Construye la URL del health check sin duplicar separadores."""
    return f"{api_url.strip().rstrip('/')}/api/v1/health"


@st.cache_data(ttl=30, show_spinner=False)
def fetch_api_health(api_url: str) -> dict[str, Any]:
    """Obtiene el estado de la API configurada."""
    try:
        request = Request(
            build_health_url(api_url),
            headers={"Accept": "application/json"},
        )
        with urlopen(request, timeout=2) as response:  # noqa: S310
            payload = json.load(response)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ApiUnavailableError("No se pudo conectar con la API.") from exc

    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise ApiUnavailableError("La API devolvió un estado no válido.")

    return payload


def render_sidebar() -> tuple[Any, str]:
    """Muestra la configuración y devuelve el manual seleccionado."""
    with st.sidebar:
        st.header("Configuración")
        api_url = st.text_input(
            "URL de la API",
            value=get_settings().api_base_url,
            help="Dirección base del servicio FastAPI.",
        )

        if st.button("Actualizar estado", use_container_width=True):
            fetch_api_health.clear()

        try:
            health = fetch_api_health(api_url)
        except ApiUnavailableError:
            st.error("API no disponible")
        else:
            version = health.get("version", "desconocida")
            st.success(f"API conectada · v{version}")

        st.divider()
        st.subheader("Manual")
        manual = st.file_uploader(
            "Carga un archivo",
            type=SUPPORTED_FILE_TYPES,
            help="PDF con texto, TXT y Markdown. Máximo 10 MiB; sin OCR.",
        )
        if manual is not None:
            size_kb = manual.size / 1024
            st.caption(f"{manual.name} · {size_kb:.1f} KB")

    return manual, api_url


def render_document_upload(manual: Any, api_url: str) -> None:
    """Solo envía archivos al pulsar el botón, nunca durante un rerun."""
    selection = (api_url.strip().rstrip("/"), manual.name, manual.file_id)
    if st.session_state.get("upload_selection") != selection:
        st.session_state["upload_selection"] = selection
        st.session_state.pop("upload_result", None)
    if st.button("Procesar y guardar", type="primary"):
        st.session_state.pop("upload_result", None)
        with st.spinner("Procesando y guardando fragmentos…"):
            try:
                result = upload_document(api_url, manual.name, manual.getvalue())
            except DocumentUploadError as exc:
                st.error(str(exc))
            else:
                st.session_state["upload_result"] = result.model_dump()
    result = st.session_state.get("upload_result")
    if result:
        st.success(f"Se guardaron {result['indexed_chunks']} fragmentos del archivo.")
        for warning in result["warnings"]:
            st.warning(warning)


def render_app() -> None:
    """Renderiza la aplicación Streamlit."""
    st.set_page_config(
        page_title="RAG Manual",
        page_icon="📚",
        layout="centered",
    )

    manual, api_url = render_sidebar()

    st.title("📚 RAG Manual")
    st.write("Consulta información de tus manuales desde una interfaz sencilla.")

    if manual is None:
        st.session_state.pop("upload_selection", None)
        st.session_state.pop("upload_result", None)
        st.info("Carga un manual desde la barra lateral para comenzar.")
    else:
        st.write(f"Manual seleccionado: **{manual.name}**")
        render_document_upload(manual, api_url)

    st.subheader("Haz una pregunta")
    with st.form("question_form"):
        question = st.text_area(
            "Pregunta",
            placeholder="Por ejemplo: ¿Cómo realizo el mantenimiento preventivo?",
            height=120,
            disabled=manual is None,
        )
        submitted = st.form_submit_button(
            "Consultar",
            type="primary",
            use_container_width=True,
            disabled=manual is None,
        )

    if submitted:
        if not question.strip():
            st.warning("Escribe una pregunta antes de continuar.")
        else:
            st.session_state["last_question"] = question.strip()
            st.info(
                "La consulta está preparada. La búsqueda sobre estos fragmentos "
                "y la generación de respuestas todavía están pendientes."
            )

    last_question = st.session_state.get("last_question")
    if last_question:
        st.caption("Consulta más reciente")
        st.markdown(f"> {last_question}")


if __name__ == "__main__":
    render_app()
