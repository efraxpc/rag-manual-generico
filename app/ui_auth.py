"""Inicio de sesión OIDC en Streamlit y token delegado para FastAPI."""

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def require_login() -> str | None:
    """Devuelve el token de la sesión actual; nunca lo guarda en cachés globales."""
    try:
        configured = bool(st.secrets["auth"]["microsoft"]["client_id"])
    except (StreamlitSecretNotFoundError, KeyError):
        configured = False
    if not configured:
        st.error("El inicio de sesión no está disponible. Contacta al administrador.")
        return None

    if not st.user.get("is_logged_in", False):
        st.session_state.clear()
        st.title("📚 RAG Manual")
        st.write(
            "Inicia sesión con tu cuenta de Microsoft para acceder a la aplicación."
        )
        if st.button("Iniciar sesión con Microsoft", type="primary"):
            st.login("microsoft")
        return None

    identity = (st.user.get("tid"), st.user.get("oid"))
    if st.session_state.get("active_user") != identity:
        st.session_state.clear()
        st.session_state["active_user"] = identity

    access_token = st.user.tokens.get("access")
    if not isinstance(access_token, str) or not access_token:
        st.warning("Tu sesión necesita renovarse. Vuelve a iniciar sesión.")
        if st.button("Volver a iniciar sesión"):
            st.session_state.clear()
            st.logout()
        return None

    with st.sidebar:
        st.write(st.user.get("name", "Usuario conectado"))
        if st.button("Cerrar sesión"):
            st.session_state.clear()
            st.logout()
            return None
    return access_token
