import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_LOCAL = PROJECT_ROOT / "scripts" / "run_local.sh"


def run_script(
    *arguments: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUN_LOCAL), *arguments],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_help_describes_restart_option() -> None:
    result = run_script("--help")

    assert result.returncode == 0
    assert "Uso: run_local.sh [start|restart]" in result.stdout
    assert "restart  Reinicia una instancia activa" in result.stdout


def test_unknown_option_returns_usage_error() -> None:
    result = run_script("unknown")

    assert result.returncode == 2
    assert "Opción desconocida: unknown" in result.stderr
    assert "Uso: run_local.sh [start|restart]" in result.stderr


def test_restart_starts_normally_without_active_instance(tmp_path: Path) -> None:
    env = os.environ | {
        "RAG_PYTHON_BIN": str(tmp_path / "missing-python"),
        "RAG_RUN_LOCAL_PID_FILE": str(tmp_path / "run_local.pid"),
    }

    result = run_script("restart", env=env)

    assert result.returncode == 1
    assert "No hay una instancia registrada" in result.stdout
    assert "No se encontró el intérprete de Python" in result.stderr


def test_restart_stops_active_launcher_before_starting(tmp_path: Path) -> None:
    ready_file = tmp_path / "ready"
    stopped_file = tmp_path / "stopped"
    pid_file = tmp_path / "run_local.pid"
    launcher_code = """
import signal
import sys
from pathlib import Path

ready_file = Path(sys.argv[1])
stopped_file = Path(sys.argv[2])


def stop(_signal_number, _frame):
    stopped_file.touch()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
ready_file.touch()
signal.pause()
"""
    launcher = subprocess.Popen(
        [sys.executable, "-c", launcher_code, str(ready_file), str(stopped_file)]
    )

    try:
        for _attempt in range(50):
            if ready_file.exists():
                break
            time.sleep(0.02)
        else:
            raise AssertionError("La instancia simulada no llegó a estar preparada")

        identity = subprocess.run(
            ["ps", "-p", str(launcher.pid), "-o", "lstart="],
            env=os.environ | {"LC_ALL": "C"},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        pid_file.write_text(f"{launcher.pid}|{identity}\n", encoding="utf-8")
        env = os.environ | {
            "RAG_PYTHON_BIN": str(tmp_path / "missing-python"),
            "RAG_RUN_LOCAL_PID_FILE": str(pid_file),
        }

        result = run_script("restart", env=env)

        assert result.returncode == 1
        assert f"Deteniendo la instancia activa (PID {launcher.pid})" in result.stdout
        assert "Instancia anterior detenida; iniciando una nueva." in result.stdout
        assert "No se encontró el intérprete de Python" in result.stderr
        assert launcher.wait(timeout=5) == 0
        assert stopped_file.exists()
    finally:
        if launcher.poll() is None:
            launcher.send_signal(signal.SIGTERM)
            launcher.wait(timeout=5)


def test_restart_forces_an_unresponsive_launcher_to_stop(tmp_path: Path) -> None:
    ready_file = tmp_path / "ready"
    pid_file = tmp_path / "run_local.pid"
    launcher_code = """
import signal
import sys
from pathlib import Path

signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(sys.argv[1]).touch()
signal.pause()
"""
    launcher = subprocess.Popen([sys.executable, "-c", launcher_code, str(ready_file)])

    try:
        for _attempt in range(50):
            if ready_file.exists():
                break
            time.sleep(0.02)
        else:
            raise AssertionError("La instancia simulada no llegó a estar preparada")

        identity = subprocess.run(
            ["ps", "-p", str(launcher.pid), "-o", "lstart="],
            env=os.environ | {"LC_ALL": "C"},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        pid_file.write_text(f"{launcher.pid}|{identity}\n", encoding="utf-8")
        env = os.environ | {
            "RAG_PYTHON_BIN": str(tmp_path / "missing-python"),
            "RAG_RUN_LOCAL_PID_FILE": str(pid_file),
        }

        result = run_script("restart", env=env)

        assert result.returncode == 1
        assert "Forzando la detención de la instancia activa" in result.stdout
        assert launcher.wait(timeout=5) == -signal.SIGKILL
    finally:
        if launcher.poll() is None:
            launcher.kill()
            launcher.wait(timeout=5)
