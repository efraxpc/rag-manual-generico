#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${RAG_PYTHON_BIN:-${PROJECT_ROOT}/.venv/bin/python}"
API_HOST="${RAG_API_HOST:-127.0.0.1}"
API_PORT="${RAG_API_PORT:-8000}"
UI_HOST="${RAG_UI_HOST:-127.0.0.1}"
UI_PORT="${RAG_UI_PORT:-8501}"
PID_FILE="${RAG_RUN_LOCAL_PID_FILE:-${PROJECT_ROOT}/.run_local.pid}"
ACTION="${1:-start}"
API_PID=""
UI_PID=""
RESTART_REQUESTED=0

usage() {
    printf 'Uso: %s [start|restart]\n' "${0##*/}"
    printf '  start    Inicia la API y la interfaz (opción predeterminada).\n'
    printf '  restart  Reinicia una instancia activa o inicia una nueva.\n'
}

process_identity() {
    local identity
    local pid=$1

    identity="$(LC_ALL=C ps -p "${pid}" -o lstart= 2>/dev/null)" || return 1
    identity="${identity#"${identity%%[![:space:]]*}"}"
    identity="${identity%"${identity##*[![:space:]]}"}"
    [[ -n "${identity}" ]] || return 1

    printf '%s\n' "${identity}"
}

legacy_launcher_pids() {
    local pid
    local script_path
    local -a command_line

    # Las versiones anteriores no creaban un archivo PID. En Linux podemos
    # reconocer el script exacto, incluso si se ejecutó con una ruta relativa.
    [[ -d /proc ]] || return 0
    while read -r pid; do
        [[ "${pid}" != "$$" && -r "/proc/${pid}/cmdline" ]] || continue
        mapfile -d '' -t command_line <"/proc/${pid}/cmdline" 2>/dev/null \
            || continue
        [[ "${command_line[0]:-}" == */bash || \
            "${command_line[0]:-}" == bash ]] || continue
        [[ "${command_line[2]:-start}" == start ]] || continue
        # Bash mantiene abierto el script en el descriptor 255 aunque este
        # haya cambiado de directorio tras arrancar desde scripts/.
        script_path="$(readlink -f -- "/proc/${pid}/fd/255" 2>/dev/null)" \
            || script_path=""
        if [[ "${script_path}" != "${PROJECT_ROOT}/scripts/run_local.sh" ]]; then
            script_path="${command_line[1]:-}"
            [[ -n "${script_path}" ]] || continue
            if [[ "${script_path}" != /* ]]; then
                script_path="/proc/${pid}/cwd/${script_path}"
            fi
            script_path="$(readlink -f -- "${script_path}" 2>/dev/null)" \
                || continue
        fi
        [[ "${script_path}" == "${PROJECT_ROOT}/scripts/run_local.sh" ]] \
            || continue
        printf '%s\n' "${pid}"
    done < <(ps -u "${UID}" -o pid=)
}

stop_legacy_launchers() {
    local pid
    local identity
    local attempt
    local state

    while read -r pid; do
        identity="$(process_identity "${pid}")" || continue
        printf 'Deteniendo instancia anterior de run_local.sh (PID %s)...\n' \
            "${pid}"
        kill -TERM "${pid}" 2>/dev/null || continue
        for ((attempt = 1; attempt <= 60; attempt++)); do
            [[ "$(process_identity "${pid}" || true)" == "${identity}" ]] \
                || break
            state="$(ps -p "${pid}" -o stat= 2>/dev/null)" || break
            [[ "${state}" != Z* ]] || break
            sleep 0.25
        done
        if ((attempt > 60)); then
            printf 'La instancia anterior (PID %s) no terminó a tiempo.\n' \
                "${pid}" >&2
            return 1
        fi
    done < <(legacy_launcher_pids)
}

registered_pid() {
    local current_identity
    local pid
    local stored_identity

    [[ -r "${PID_FILE}" ]] || return 1
    IFS='|' read -r pid stored_identity <"${PID_FILE}" || return 1
    [[ "${pid}" =~ ^[1-9][0-9]*$ ]] || return 1
    kill -0 "${pid}" 2>/dev/null || return 1
    current_identity="$(process_identity "${pid}")" || return 1
    [[ "${stored_identity}" == "${current_identity}" ]] || return 1

    printf '%s\n' "${pid}"
}

register_launcher() {
    local active_pid
    local identity
    local temporary_pid_file="${PID_FILE}.$$"

    if active_pid="$(registered_pid)"; then
        printf 'Los servicios locales ya están activos (PID %s).\n' \
            "${active_pid}" >&2
        printf 'Usa "%s restart" para reiniciarlos.\n' "${0##*/}" >&2
        return 1
    fi

    identity="$(process_identity "$$")" || return 1
    printf '%s|%s\n' "$$" "${identity}" >"${temporary_pid_file}" || return 1
    mv -- "${temporary_pid_file}" "${PID_FILE}"
}

unregister_launcher() {
    local pid
    local stored_identity

    if [[ -r "${PID_FILE}" ]]; then
        IFS='|' read -r pid stored_identity <"${PID_FILE}" || true
        if [[ "${pid:-}" == "$$" ]]; then
            rm -f -- "${PID_FILE}"
        fi
    fi
}

signal_services() {
    if [[ -n "${UI_PID}" ]] && kill -0 "${UI_PID}" 2>/dev/null; then
        kill "${UI_PID}" 2>/dev/null || true
    fi

    if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
        kill "${API_PID}" 2>/dev/null || true
    fi
}

stop_services() {
    signal_services

    [[ -n "${UI_PID}" ]] && wait "${UI_PID}" 2>/dev/null || true
    [[ -n "${API_PID}" ]] && wait "${API_PID}" 2>/dev/null || true

    API_PID=""
    UI_PID=""
}

cleanup() {
    local exit_code=$?

    trap - EXIT HUP INT TERM USR1
    stop_services
    unregister_launcher

    printf '\nServicios locales detenidos.\n'
    exit "${exit_code}"
}

request_restart() {
    RESTART_REQUESTED=1
    signal_services
}

check_ports_available() {
    "${PYTHON_BIN}" - "${API_HOST}" "${API_PORT}" "${UI_HOST}" "${UI_PORT}" <<'PY'
import socket
import sys
from contextlib import ExitStack

with ExitStack() as stack:
    for name, host, port in (
        ("API", sys.argv[1], sys.argv[2]),
        ("interfaz", sys.argv[3], sys.argv[4]),
    ):
        try:
            if not 1 <= int(port) <= 65535:
                raise ValueError("el puerto debe estar entre 1 y 65535")
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            sock = stack.enter_context(socket.socket(family, socket.SOCK_STREAM))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, int(port)))
            sock.listen(1)
        except (OSError, ValueError) as exc:
            print(f"No se puede iniciar {name} en {host}:{port}: {exc}.",
                  file=sys.stderr)
            print("Comprueba qué proceso ocupa el puerto. Usa restart si pertenece "
                  "a una instancia anterior de este script.", file=sys.stderr)
            sys.exit(1)
PY
}

health_url() {
    local host=$1
    case "${host}" in
        0.0.0.0) host=127.0.0.1 ;;
        ::) host=::1 ;;
    esac
    [[ "${host}" != *:* ]] || host="[${host}]"
    printf 'http://%s:%s%s\n' "${host}" "$2" "$3"
}

service_is_ready() {
    RAG_HEALTH_URL="$1" \
        "${PYTHON_BIN}" -c \
        'import os, urllib.request; urllib.request.urlopen(os.environ["RAG_HEALTH_URL"], timeout=0.5).close()' \
        >/dev/null 2>&1
}

wait_for_service() {
    local pid=$1
    local url=$2
    local attempt

    for ((attempt = 1; attempt <= 60; attempt++)); do
        if ((RESTART_REQUESTED)) || ! kill -0 "${pid}" 2>/dev/null; then
            return 1
        fi

        if service_is_ready "${url}"; then
            kill -0 "${pid}" 2>/dev/null
            return $?
        fi

        sleep 0.25
    done

    return 1
}

start_services() {
    check_ports_available || return 1

    printf 'Iniciando API en http://%s:%s ...\n' "${API_HOST}" "${API_PORT}"
    "${PYTHON_BIN}" -m uvicorn app.main:app \
        --host "${API_HOST}" \
        --port "${API_PORT}" \
        --reload &
    API_PID=$!

    if ! wait_for_service "${API_PID}" "${API_HEALTH_URL}"; then
        if ((RESTART_REQUESTED == 0)); then
            printf 'La API no pudo iniciarse en %s.\n' \
                "${APP_API_BASE_URL}" >&2
        fi
        return 1
    fi

    if ((RESTART_REQUESTED)); then
        return 1
    fi

    printf 'Iniciando interfaz en http://%s:%s ...\n' "${UI_HOST}" "${UI_PORT}"
    "${PYTHON_BIN}" -m streamlit run app/streamlit_app.py \
        --server.address "${UI_HOST}" \
        --server.port "${UI_PORT}" \
        --browser.gatherUsageStats false &
    UI_PID=$!

    if ! wait_for_service "${UI_PID}" "${UI_HEALTH_URL}"; then
        if ((RESTART_REQUESTED == 0)); then
            printf 'La interfaz no pudo iniciarse en http://%s:%s.\n' \
                "${UI_HOST}" "${UI_PORT}" >&2
        fi
        return 1
    fi

    printf '\nRAG Manual está disponible:\n'
    printf '  API:      %s\n' "${APP_API_BASE_URL}"
    printf '  Interfaz: http://%s:%s\n' "${UI_HOST}" "${UI_PORT}"
    printf 'Pulsa Ctrl+C para detener ambos servicios.\n\n'
}

if (($# > 1)); then
    usage >&2
    exit 2
fi

case "${ACTION}" in
    start)
        ;;
    restart)
        if active_pid="$(registered_pid)"; then
            if kill -USR1 "${active_pid}" 2>/dev/null; then
                printf 'Solicitud de reinicio enviada (PID %s).\n' "${active_pid}"
                exit 0
            fi
        fi
        printf 'No hay una instancia registrada; comprobando instancias anteriores.\n'
        ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        printf 'Opción desconocida: %s\n' "${ACTION}" >&2
        usage >&2
        exit 2
        ;;
esac

if [[ ! -x "${PYTHON_BIN}" ]]; then
    printf 'No se encontró el intérprete de Python en %s.\n' "${PYTHON_BIN}" >&2
    printf 'Crea el entorno con: python -m venv .venv\n' >&2
    exit 1
fi

if ! "${PYTHON_BIN}" -c 'import streamlit, uvicorn' >/dev/null 2>&1; then
    printf 'Faltan dependencias. Ejecuta: pip install -e ".[dev]"\n' >&2
    exit 1
fi

cd "${PROJECT_ROOT}"
export APP_API_BASE_URL="${APP_API_BASE_URL:-http://${API_HOST}:${API_PORT}}"
API_HEALTH_URL="$(health_url "${API_HOST}" "${API_PORT}" /api/v1/health)"
UI_HEALTH_URL="$(health_url "${UI_HOST}" "${UI_PORT}" /_stcore/health)"

if [[ "${ACTION}" == restart ]] && ! stop_legacy_launchers; then
    exit 1
fi

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
trap request_restart USR1

if ! register_launcher; then
    exit 1
fi

while true; do
    start_status=0
    start_services || start_status=$?

    if ((RESTART_REQUESTED)); then
        stop_services
        RESTART_REQUESTED=0
        printf '\nReiniciando servicios locales...\n'
        continue
    fi

    if ((start_status != 0)); then
        exit "${start_status}"
    fi

    set +e
    wait -n "${API_PID}" "${UI_PID}"
    exit_code=$?
    set -e

    if ((RESTART_REQUESTED)); then
        stop_services
        RESTART_REQUESTED=0
        printf '\nReiniciando servicios locales...\n'
        continue
    fi

    printf 'Uno de los servicios terminó inesperadamente.\n' >&2
    exit "${exit_code}"
done
