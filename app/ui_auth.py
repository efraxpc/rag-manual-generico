"""Inicio de sesión OIDC en Streamlit y token delegado para FastAPI."""

from html import escape
from urllib.parse import urlsplit, urlunsplit

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

LOGIN_PROVIDER = "microsoft"
LOGIN_REQUEST_PARAM = "_auth_login"


def _configured_auth_home() -> str | None:
    """Devuelve la portada que comparte origen con el callback OIDC."""
    redirect_uri = st.secrets["auth"].get("redirect_uri")
    if not isinstance(redirect_uri, str):
        return None

    parsed = urlsplit(redirect_uri)
    callback_suffix = "/oauth2callback"
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.path.endswith(callback_suffix)
    ):
        return None

    home_path = parsed.path.removesuffix(callback_suffix) or "/"
    if not home_path.endswith("/"):
        home_path = f"{home_path}/"
    return urlunsplit((parsed.scheme, parsed.netloc, home_path, "", ""))


def _origin(url: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    if not parsed.scheme or not parsed.hostname:
        return None
    if port is None:
        port = {"http": 80, "https": 443}.get(parsed.scheme.lower())
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def _login_requested() -> bool:
    if st.query_params.get(LOGIN_REQUEST_PARAM) != LOGIN_PROVIDER:
        return False
    del st.query_params[LOGIN_REQUEST_PARAM]
    return True


def _render_canonical_login(auth_home: str) -> None:
    """Navega en la misma pestaña para conservar las cookies del flujo OIDC."""
    action = escape(auth_home, quote=True)
    parameter = escape(LOGIN_REQUEST_PARAM, quote=True)
    provider = escape(LOGIN_PROVIDER, quote=True)
    st.markdown(
        f"""
        <form action="{action}" method="get" target="_self">
          <input type="hidden" name="{parameter}" value="{provider}">
          <button type="submit">Iniciar sesión con Microsoft</button>
        </form>
        """,
        unsafe_allow_html=True,
    )


def require_login() -> str | None:
    """Devuelve el token de la sesión actual; nunca lo guarda en cachés globales."""
    try:
        configured = bool(st.secrets["auth"]["microsoft"]["client_id"])
    except (StreamlitSecretNotFoundError, KeyError):
        configured = False
    if not configured:
        st.error("El inicio de sesión no está disponible. Contacta al administrador.")
        return None

    if not st.user.is_logged_in:
        st.session_state.clear()
        auth_home = _configured_auth_home()
        current_url = st.context.url
        different_auth_origin = (
            auth_home is not None
            and isinstance(current_url, str)
            and _origin(current_url) != _origin(auth_home)
        )
        if _login_requested() and not different_auth_origin:
            st.login(LOGIN_PROVIDER)
            return None

        st.title("📚 RAG Manual")
        st.write(
            "Inicia sesión con tu cuenta de Microsoft para acceder a la aplicación."
        )
        if different_auth_origin:
            _render_canonical_login(auth_home)
        elif st.button("Iniciar sesión con Microsoft", type="primary"):
            st.login(LOGIN_PROVIDER)
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
