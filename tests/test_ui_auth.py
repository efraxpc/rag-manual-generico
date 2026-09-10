from unittest.mock import MagicMock

import pytest
from streamlit.errors import StreamlitSecretNotFoundError

from app import streamlit_app, ui_auth


class FakeUser(dict):
    def __init__(self, *, token: str | None = "token-one", **kwargs: object) -> None:
        super().__init__(is_logged_in=True, tid="tenant", oid="user-one", name="Ana")
        self.update(kwargs)
        self.tokens = {"access": token} if token else {}

    @property
    def is_logged_in(self) -> bool:
        return bool(self["is_logged_in"])


@pytest.fixture
def ui(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    ui = MagicMock()
    ui.secrets = {
        "auth": {
            "redirect_uri": "http://localhost:8501/oauth2callback",
            "microsoft": {"client_id": "frontend"},
        }
    }
    ui.user = FakeUser()
    ui.session_state = {}
    ui.query_params = {}
    ui.context.url = "http://localhost:8501/"
    ui.button.return_value = False
    monkeypatch.setattr(ui_auth, "st", ui)
    return ui


def test_login_button_starts_microsoft_flow(ui: MagicMock) -> None:
    ui.user = FakeUser(is_logged_in=False)
    ui.button.return_value = True
    assert ui_auth.require_login() is None
    ui.login.assert_called_once_with("microsoft")


def test_login_uses_callback_origin_before_starting_flow(ui: MagicMock) -> None:
    ui.user = FakeUser(is_logged_in=False)
    ui.context.url = "http://127.0.0.1:8501/"

    assert ui_auth.require_login() is None

    ui.button.assert_not_called()
    html = ui.markdown.call_args.args[0]
    assert 'action="http://localhost:8501/"' in html
    assert 'target="_self"' in html
    assert f'name="{ui_auth.LOGIN_REQUEST_PARAM}"' in html


def test_canonical_login_request_redirects_to_microsoft_without_login_screen(
    ui: MagicMock,
) -> None:
    ui.user = FakeUser(is_logged_in=False)
    ui.query_params[ui_auth.LOGIN_REQUEST_PARAM] = "microsoft"

    assert ui_auth.require_login() is None

    ui.login.assert_called_once_with("microsoft")
    ui.title.assert_not_called()
    ui.write.assert_not_called()
    assert ui_auth.LOGIN_REQUEST_PARAM not in ui.query_params


def test_no_configuration_shows_error_and_does_not_login(ui: MagicMock) -> None:
    ui.secrets = {}
    assert ui_auth.require_login() is None
    ui.error.assert_called_once()
    ui.login.assert_not_called()


def test_missing_secrets_file_is_controlled(ui: MagicMock) -> None:
    ui.secrets = MagicMock()
    ui.secrets.__getitem__.side_effect = StreamlitSecretNotFoundError("missing file")
    assert ui_auth.require_login() is None
    ui.error.assert_called_once()


def test_only_returns_access_token_without_displaying_it(ui: MagicMock) -> None:
    assert ui_auth.require_login() == "token-one"
    assert "token-one" not in str(ui.write.call_args_list)
    assert "token-one" not in str(ui.session_state)


def test_authenticated_user_skips_login_screen(ui: MagicMock) -> None:
    assert ui_auth.require_login() == "token-one"
    ui.login.assert_not_called()
    ui.title.assert_not_called()
    assert "Inicia sesión con tu cuenta de Microsoft" not in str(
        ui.write.call_args_list
    )


def test_expired_token_requests_reauthentication(ui: MagicMock) -> None:
    ui.user = FakeUser(token=None)
    ui.button.return_value = True
    assert ui_auth.require_login() is None
    ui.logout.assert_called_once()
    assert ui.session_state == {}


def test_logout_clears_document_state(ui: MagicMock) -> None:
    ui.session_state = {"active_user": ("tenant", "user-one"), "upload_result": "old"}
    ui.button.return_value = True
    assert ui_auth.require_login() is None
    ui.logout.assert_called_once()
    assert ui.session_state == {}


def test_account_switch_clears_old_uploads_and_uses_new_token(ui: MagicMock) -> None:
    assert ui_auth.require_login() == "token-one"
    ui.session_state["upload_result"] = "old"
    ui.user = FakeUser(token="token-two", oid="user-two")
    assert ui_auth.require_login() == "token-two"
    assert "upload_result" not in ui.session_state
    assert ui.session_state["active_user"] == ("tenant", "user-two")


def test_app_does_not_render_upload_until_logged_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui = MagicMock()
    monkeypatch.setattr(streamlit_app, "st", ui)
    monkeypatch.setattr(streamlit_app, "require_login", lambda: None)
    sidebar = MagicMock()
    monkeypatch.setattr(streamlit_app, "render_sidebar", sidebar)
    streamlit_app.render_app()
    sidebar.assert_not_called()


def test_app_renders_upload_view_after_successful_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui = MagicMock()
    ui.form_submit_button.return_value = False
    monkeypatch.setattr(streamlit_app, "st", ui)
    monkeypatch.setattr(streamlit_app, "require_login", lambda: "access-token")
    sidebar = MagicMock(return_value=(None, "http://api.example"))
    monkeypatch.setattr(streamlit_app, "render_sidebar", sidebar)

    streamlit_app.render_app()

    sidebar.assert_called_once_with()
    assert "Carga un manual desde la barra lateral" in str(ui.info.call_args_list)


def test_sidebar_uses_configured_api_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui = MagicMock()
    ui.button.return_value = False
    ui.file_uploader.return_value = None
    settings = MagicMock(api_base_url="https://trusted-api.example")
    monkeypatch.setattr(streamlit_app, "st", ui)
    monkeypatch.setattr(streamlit_app, "get_settings", lambda: settings)
    monkeypatch.setattr(streamlit_app, "fetch_api_health", lambda url: {"version": "1"})
    _, url = streamlit_app.render_sidebar()
    assert url == "https://trusted-api.example"
    ui.text_input.assert_not_called()
