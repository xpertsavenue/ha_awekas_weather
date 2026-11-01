# Awekas Weather – Dev Container

This directory contains a **Home Assistant development environment** for VS Code Dev Containers. It lets you develop, test and debug the `awekas_weather` custom integration without installing anything on your machine.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine on Linux)
- [Visual Studio Code](https://code.visualstudio.com/) with the **Dev Containers** extension (`ms-vscode-remote.remote-containers`)

Open the repository in VS Code and choose **Reopen in Container**, or run `Dev Containers: Reopen in Container` from the Command Palette.

> **Windows:** the setup relies on symlinks inside `config/`, and a bind mount of an NTFS folder is slow. The most reliable option is **`Dev Containers: Clone Repository in Container Volume`**, or a clone inside the WSL file system (`\\wsl$\...`). Make sure Git checks out LF line endings. The repository enforces them with `.gitattributes`.

## What happens when the container is built

| Step | What happens |
|------|-------------|
| Base image | `mcr.microsoft.com/devcontainers/python:3.14` |
| System packages | `git`, `curl`, `build-essential`, `ffmpeg`, `libturbojpeg0-dev`, `libpcap-dev` |
| Python packages | `requirements_test.txt` (includes `requirements_dev.txt`) is installed into the virtualenv **`/opt/venv` inside the image** |
| Ports | `8123` (Home Assistant UI) and `5678` (debugpy) are published by Docker (`appPort`) |
| `postCreateCommand` | runs `scripts/setup.sh` |
| `postStartCommand` | starts Home Assistant in the background on every container start, console output in `/tmp/ha-console.log` |

**After changing `requirements_*.txt`, run `Dev Containers: Rebuild Container`.** The packages are part of the image. `homeassistant` in `requirements_dev.txt` and `pytest-homeassistant-custom-component` in `requirements_test.txt` must be updated together, because the test package pins the matching Home Assistant version.

## `scripts/setup.sh`

Prepares the git-ignored Home Assistant config directory `config/`:

| Link in `config/` | Points to | If a real file/directory is in the way |
|---|---|---|
| `configuration.yaml` | `.devcontainer/configuration.yaml` | moved to `config/.setup-backups/`, then linked |
| `custom_components/awekas_weather` | `custom_components/awekas_weather` | moved to `config/.setup-backups/`, then linked |
| `.storage/lovelace_dashboards` | `.devcontainer/lovelace_dashboards` | kept, with a warning |
| `.storage/lovelace.dashboard_test` | `.devcontainer/lovelace.dashboard_test` | kept, with a warning |

Home Assistant replaces the symlinks in `.storage/` with real files when you save a dashboard in the UI. To return to the versioned dashboards, delete those files and run the script again.

## VS Code tasks

Run them with `Tasks: Run Task` from the Command Palette.

| Task | Description |
|------|-------------|
| `Home Assistant: Start` | Runs `setup.sh`, then starts HA in debug mode, unless it is already running (default build task, `Ctrl+Shift+B`) |
| `Home Assistant: Stop` | Stops the HA instance started by `scripts/ha.sh` |
| `Home Assistant: Restart` | Stop, then start |
| `Home Assistant: Setup` | Runs `setup.sh` only |
| `Run Tests` | `pytest` with coverage (default test task) |
| `Lint` | `ruff check` and `ruff format --check` |
| `Format` | `ruff check --fix` and `ruff format` |

Home Assistant starts automatically with the container. The UI is available at <http://localhost:8123> about 20 seconds later. Use `Home Assistant: Restart` to load code changes.

## Debugging

- **Home Assistant Core (Debug)** (`.vscode/launch.json`) starts HA under the debugger. Stop the automatically started instance first with `Home Assistant: Stop`, both use port 8123.
- **Attach to running Home Assistant** attaches to an instance started with the task. The `debugpy` integration in `configuration.yaml` listens on port 5678.

## Customisation

- **Log levels and recorder retention:** edit `.devcontainer/configuration.yaml`. The integration logs at `debug` level, and the recorder keeps 1 day of history.
- **Additional mounts (SSH keys, UI cards):** see the commented entries in `devcontainer.json`.

## File structure

```
.devcontainer/
├── Dockerfile                  # Image with all Python packages in /opt/venv
├── devcontainer.json           # VS Code Dev Container configuration
├── configuration.yaml          # HA configuration (linked into config/)
├── lovelace_dashboards         # Dashboard registry (linked into config/.storage/)
├── lovelace.dashboard_test     # Test dashboard (linked into config/.storage/)
└── README.md

scripts/
├── setup.sh                    # Prepares config/
└── ha.sh                       # start / stop / restart

config/                         # HA runtime config, git-ignored
custom_components/awekas_weather/   # Integration source code
tests/                          # pytest tests
```
