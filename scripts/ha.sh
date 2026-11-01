#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ha.sh – Helper script to manage the Home Assistant dev instance
#
# Usage:
#   ./scripts/ha.sh start    – Launch Home Assistant in debug mode
#   ./scripts/ha.sh stop     – Stop Home Assistant
#   ./scripts/ha.sh restart  – Stop then start Home Assistant
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONFIG_DIR="${WORKSPACE}/config"

# Login shells drop the virtualenv of the image from PATH
VENV_DIR="${VIRTUAL_ENV:-/opt/venv}"
if [ -x "${VENV_DIR}/bin/python" ]; then
    export PATH="${VENV_DIR}/bin:${PATH}"
fi

HA_PROCESS="${HA_PROCESS:-hass}"
# Only match the instance started by this script
HA_PATTERN="${HA_PROCESS} --config ${CONFIG_DIR}"

ha_start() {
    # The container starts Home Assistant automatically (postStartCommand)
    if pgrep -f -- "${HA_PATTERN}" >/dev/null; then
        echo "[ha.sh] Home Assistant is already running, use 'restart' to restart it."
        return
    fi

    echo "[ha.sh] Initializing environment …"
    bash "${SCRIPT_DIR}/setup.sh"

    if ! command -v "${HA_PROCESS}" >/dev/null 2>&1; then
        echo "[ha.sh] ERROR: '${HA_PROCESS}' command not found in PATH." >&2
        exit 1
    fi

    echo "[ha.sh] Starting Home Assistant with config: ${CONFIG_DIR}"
    cd "${WORKSPACE}"
    exec "${HA_PROCESS}" --config "${CONFIG_DIR}" --debug
}

ha_stop() {
    echo "[ha.sh] Stopping Home Assistant …"
    if pkill -f -- "${HA_PATTERN}"; then
        # Give the process a moment to shut down cleanly
        for _ in $(seq 1 30); do
            pgrep -f -- "${HA_PATTERN}" >/dev/null || break
            sleep 1
        done
        echo "[ha.sh] Home Assistant stopped."
    else
        echo "[ha.sh] No running Home Assistant process found."
    fi
}

case "${1:-}" in
    start)   ha_start ;;
    stop)    ha_stop ;;
    restart) ha_stop; ha_start ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac
