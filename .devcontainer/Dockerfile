FROM mcr.microsoft.com/devcontainers/base:jammy

ARG USERNAME=vscode
ARG DEBIAN_FRONTEND=noninteractive

# Common build deps for Python packages (psycopg2, uvloop, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    libssl-dev \
    libffi-dev \
    libpq-dev \
    libopencv-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Helpful environment for Python tooling
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 

# Ensure the workspace is safe for Git inside containers (useful for pre-commit/CI)
RUN git config --system --add safe.directory "*"

# Create a directory that Jupyter can use by default inside the container
RUN mkdir -p /home/${USERNAME}/.jupyter && chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/.jupyter
