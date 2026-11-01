FROM mcr.microsoft.com/devcontainers/python:3.14

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH}

# Remove the yarn repository pre-configured in the base image (GPG key is invalid)
RUN rm -f /etc/apt/sources.list.d/yarn.list

RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    ffmpeg libturbojpeg0-dev \
    libpcap-dev libpcap0.8-dev \
    && rm -rf /var/lib/apt/lists/*

# Python packages live in the image instead of the workspace mount, which is
# slow on Windows and macOS hosts. Rebuild the container after changing the
# requirements files.
COPY requirements_dev.txt requirements_test.txt /tmp/requirements/
RUN python -m venv /opt/venv \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements/requirements_test.txt \
    && chown -R vscode:vscode /opt/venv \
    && rm -rf /tmp/requirements
