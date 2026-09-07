import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

RUN_LOCAL = Path(__file__).resolve().parents[1] / "scripts" / "run_local.sh"
SERVICE_CODE = """
if __name__ == "__main__":
    import json
    import os
    import sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    if "--port" in sys.argv:
        port_option = "--port"
    else:
        port_option = "--server.port"
        if os.environ.get("RAG_TEST_UI_FAIL"):
            sys.exit(1)
    port = int(sys.argv[sys.argv.index(port_option) + 1])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"pid": os.getpid()}).encode())

        def log_message(self, *args):
            pass

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""
LEGACY_SCRIPT = """#!/usr/bin/env bash
set -Eeuo pipefail
main() {
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
    trap 'trap - EXIT INT TERM; kill "$api_pid" "$ui_pid" 2>/dev/null || true;
          wait "$api_pid" "$ui_pid" 2>/dev/null || true; exit 0' EXIT INT TERM
    "$RAG_PYTHON_BIN" -m uvicorn app.main:app --port "$RAG_API_PORT" &
    api_pid=$!
    "$RAG_PYTHON_BIN" -m streamlit run app/streamlit_app.py \
        --server.port "$RAG_UI_PORT" &
    ui_pid=$!
    wait -n "$api_pid" "$ui_pid"
}
main
"""


def service_pid(port: str) -> int | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=0.2) as resp:
            return json.load(resp)["pid"]
    except (OSError, urllib.error.URLError):
        return None


def wait_for_pid(port: str, previous: int | None = None) -> int:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        pid = service_pid(port)
        if pid is not None and pid != previous:
            return pid
        time.sleep(0.05)
    raise AssertionError(f"El servicio en {port} no arrancó/reinició")


def wait_for_available(log: Path, count: int = 1) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if log.read_text().count("RAG Manual está disponible") >= count:
            return
        time.sleep(0.05)
    raise AssertionError(log.read_text())


@contextmanager
def running_process(
    command: list[str], project: Path, env: dict[str, str], log_name: str
) -> Iterator[subprocess.Popen[str]]:
    with (project / log_name).open("w") as log:
        process = subprocess.Popen(
            command,
            cwd=project / "scripts",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
                raise


@pytest.fixture
def local_project(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "run_local.sh"
    script.write_text(RUN_LOCAL.read_text())
    script.chmod(0o755)
    for module in ("uvicorn", "streamlit"):
        (tmp_path / f"{module}.py").write_text(SERVICE_CODE)
    with socket.socket() as api_socket, socket.socket() as ui_socket:
        api_socket.bind(("127.0.0.1", 0))
        ui_socket.bind(("127.0.0.1", 0))
        api_port = str(api_socket.getsockname()[1])
        ui_port = str(ui_socket.getsockname()[1])
    env = os.environ | {
        "PYTHONPATH": str(tmp_path),
        "RAG_PYTHON_BIN": sys.executable,
        "RAG_API_HOST": "127.0.0.1",
        "RAG_API_PORT": api_port,
        "RAG_UI_HOST": "127.0.0.1",
        "RAG_UI_PORT": ui_port,
        "RAG_RUN_LOCAL_PID_FILE": str(tmp_path / "run_local.pid"),
        # La URL de la interfaz puede ser externa; el arranque debe comprobar
        # la API que acaba de lanzar, no esa URL.
        "APP_API_BASE_URL": "http://127.0.0.1:1",
    }
    return tmp_path, env


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="Recuperación Linux")
def test_restart_recovers_legacy_launcher_without_pid_file(
    local_project: tuple[Path, dict[str, str]],
) -> None:
    project, env = local_project
    script = project / "scripts" / "run_local.sh"
    script.write_text(LEGACY_SCRIPT)
    with running_process(["./run_local.sh"], project, env, "legacy.log") as legacy:
        old_api = wait_for_pid(env["RAG_API_PORT"])
        old_ui = wait_for_pid(env["RAG_UI_PORT"])
        assert not Path(env["RAG_RUN_LOCAL_PID_FILE"]).exists()
        script.write_text(RUN_LOCAL.read_text())

        with running_process(
            ["./run_local.sh", "restart"], project, env, "restart.log"
        ) as replacement:
            wait_for_pid(env["RAG_API_PORT"], old_api)
            wait_for_pid(env["RAG_UI_PORT"], old_ui)
            assert legacy.wait(timeout=5) == 0
            assert replacement.poll() is None
            wait_for_available(project / "restart.log")
        output = (project / "restart.log").read_text()
        assert (
            f"Deteniendo instancia anterior de run_local.sh (PID {legacy.pid})"
            in output
        )
        assert "RAG Manual está disponible" in output
        assert "Address already in use" not in output
    assert service_pid(env["RAG_API_PORT"]) is None
    assert service_pid(env["RAG_UI_PORT"]) is None
    assert not Path(env["RAG_RUN_LOCAL_PID_FILE"]).exists()


def test_registered_restart_replaces_both_services(
    local_project: tuple[Path, dict[str, str]],
) -> None:
    project, env = local_project
    with running_process(["./run_local.sh"], project, env, "start.log") as launcher:
        old_api = wait_for_pid(env["RAG_API_PORT"])
        old_ui = wait_for_pid(env["RAG_UI_PORT"])
        wait_for_available(project / "start.log")
        result = subprocess.run(
            ["./run_local.sh", "restart"],
            cwd=project / "scripts",
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        wait_for_pid(env["RAG_API_PORT"], old_api)
        wait_for_pid(env["RAG_UI_PORT"], old_ui)
        assert launcher.poll() is None
        wait_for_available(project / "start.log", count=2)
    assert service_pid(env["RAG_API_PORT"]) is None
    assert service_pid(env["RAG_UI_PORT"]) is None
    assert not Path(env["RAG_RUN_LOCAL_PID_FILE"]).exists()


@pytest.mark.parametrize("port_key", ["RAG_API_PORT", "RAG_UI_PORT"])
def test_occupied_port_does_not_report_success_or_stop_unrelated_process(
    local_project: tuple[Path, dict[str, str]], port_key: str
) -> None:
    project, env = local_project
    port = env[port_key]
    with running_process(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", port],
        project,
        env,
        "unrelated.log",
    ) as unrelated:
        wait_for_pid(port)
        result = subprocess.run(
            ["./run_local.sh", "restart"],
            cwd=project / "scripts",
            env=env,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        assert result.returncode == 1
        assert f"127.0.0.1:{port}" in result.stderr
        assert "No se puede iniciar" in result.stderr
        assert "RAG Manual está disponible" not in result.stdout
        assert "Iniciando API" not in result.stdout
        assert unrelated.poll() is None
        assert service_pid(port) == unrelated.pid


def test_ui_start_failure_does_not_report_success(
    local_project: tuple[Path, dict[str, str]],
) -> None:
    project, env = local_project
    env["RAG_TEST_UI_FAIL"] = "1"
    result = subprocess.run(
        ["./run_local.sh"],
        cwd=project / "scripts",
        env=env,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    assert result.returncode == 1
    assert "La interfaz no pudo iniciarse" in result.stderr
    assert "RAG Manual está disponible" not in result.stdout
    assert service_pid(env["RAG_API_PORT"]) is None
    assert not Path(env["RAG_RUN_LOCAL_PID_FILE"]).exists()
