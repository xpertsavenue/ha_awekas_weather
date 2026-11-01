#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup.sh – initialise the Home Assistant config directory of the dev container
# Run automatically via postCreateCommand in devcontainer.json and before
# every start of Home Assistant by scripts/ha.sh.
#
# Python packages are installed in the container image, see
# .devcontainer/Dockerfile. Rebuild the container after changing them.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
CONFIG_DIR="${WORKSPACE}/config"
BACKUP_DIR="${CONFIG_DIR}/.setup-backups"
DEVCONTAINER_DIR="${WORKSPACE}/.devcontainer"
COMPONENT_SRC="${WORKSPACE}/custom_components/awekas_weather"

# Login shells drop the virtualenv of the image from PATH
VENV_DIR="${VIRTUAL_ENV:-/opt/venv}"
if [ -x "${VENV_DIR}/bin/python" ]; then
    export PATH="${VENV_DIR}/bin:${PATH}"
fi

for required in "${DEVCONTAINER_DIR}/configuration.yaml" "${COMPONENT_SRC}"; do
    if [ ! -e "${required}" ]; then
        echo "ERROR: not found: ${required}" >&2
        exit 1
    fi
done

if ! python -c "import homeassistant" 2>/dev/null; then
    echo "ERROR: Home Assistant is not installed in $(command -v python)." >&2
    echo "       Rebuild the dev container to install the requirements." >&2
    exit 1
fi

echo "──────────────────────────────────────────"
echo " Awekas Weather – Container initialisation"
echo "──────────────────────────────────────────"

# ensure_symlink SRC DST ON_CONFLICT
#   ON_CONFLICT=replace: an existing real file or directory is moved to a
#                        backup and replaced by the symlink
#   ON_CONFLICT=keep:    an existing real file is kept (Home Assistant replaces
#                        symlinks in .storage with real files when saving)
ensure_symlink() {
    local src="$1" dst="$2" on_conflict="$3"

    if [ -L "${dst}" ]; then
        if [ "$(readlink "${dst}")" = "${src}" ] && [ -e "${dst}" ]; then
            echo "      Symlink already exists."
            return
        fi
        rm -f "${dst}"
    elif [ -e "${dst}" ]; then
        if [ "${on_conflict}" = "keep" ]; then
            echo "      WARNING: ${dst} is not a symlink, keeping it."
            echo "      Delete it and re-run this script to use ${src}."
            return
        fi
        # Outside of custom_components, Home Assistant must not load backups
        local backup
        backup="${BACKUP_DIR}/$(basename "${dst}")-$(date +%Y%m%d%H%M%S)"
        echo "      WARNING: ${dst} is not a symlink, moving it to ${backup}."
        mkdir -p "${BACKUP_DIR}"
        mv "${dst}" "${backup}"
    fi

    ln -s "${src}" "${dst}"
    echo "      Symlink created."
}

mkdir -p "${CONFIG_DIR}/custom_components" "${CONFIG_DIR}/.storage"

echo "[1/4] Linking configuration.yaml …"
ensure_symlink "${DEVCONTAINER_DIR}/configuration.yaml" \
    "${CONFIG_DIR}/configuration.yaml" replace

echo "[2/4] Linking custom_components/awekas_weather …"
ensure_symlink "${COMPONENT_SRC}" \
    "${CONFIG_DIR}/custom_components/awekas_weather" replace

echo "[3/4] Linking the Lovelace dashboard registry …"
ensure_symlink "${DEVCONTAINER_DIR}/lovelace_dashboards" \
    "${CONFIG_DIR}/.storage/lovelace_dashboards" keep

echo "[4/4] Linking the test dashboard …"
ensure_symlink "${DEVCONTAINER_DIR}/lovelace.dashboard_test" \
    "${CONFIG_DIR}/.storage/lovelace.dashboard_test" keep

echo ""
echo "✔ Setup complete. Happy coding!"
