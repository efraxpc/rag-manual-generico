"""Interfaz web básica para RAG Manual."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

from app.core.config import get_settings

SUPPORTED_FILE_TYPES = ["pdf", "txt", "md"]


class ApiUnavailableError(RuntimeError):
    """Indica que la interfaz no pudo consultar el estado de la API."""


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


def render_sidebar() -> Any:
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
            help="Formatos admitidos: PDF, TXT y Markdown.",
        )
        if manual is not None:
            size_kb = manual.size / 1024
            st.caption(f"{manual.name} · {size_kb:.1f} KB")

    return manual


def render_app() -> None:
    """Renderiza la aplicación Streamlit."""
    st.set_page_config(
        page_title="RAG Manual",
        page_icon="📚",
        layout="centered",
    )

    manual = render_sidebar()

    st.title("📚 RAG Manual")
    st.write("Consulta información de tus manuales desde una interfaz sencilla.")

    if manual is None:
        st.info("Carga un manual desde la barra lateral para comenzar.")
    else:
        st.success(f"Manual **{manual.name}** listo para procesar.")

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
                "La consulta está preparada. Falta conectar el procesamiento "
                "del documento y el endpoint RAG para generar una respuesta."
            )

    last_question = st.session_state.get("last_question")
    if last_question:
        st.caption("Consulta más reciente")
        st.markdown(f"> {last_question}")


if __name__ == "__main__":
    render_app()
