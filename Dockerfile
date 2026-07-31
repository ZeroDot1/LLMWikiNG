FROM python:3-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    iptables \
    iproute2 \
    git \
    ripgrep \
    jq \
    sqlite3 \
    xz-utils \
    libgomp1 \
    build-essential \
    gcc \
    libffi-dev \
    clang \
    libclang-dev \
    cmake \
    pkg-config \
    libssl-dev \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && CARGO_BUILD_JOBS=2 cargo install qmd-cli \
    && cp "$HOME/.cargo/bin/qmd" /usr/local/bin/qmd \
    && rm -rf "$HOME/.cargo" "$HOME/.rustup"

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools cffi \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential gcc libffi-dev clang libclang-dev cmake pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN mkdir -p data raw output_docs wikis/main /var/lib/tailscale /config/tailscale

RUN chmod +x run.py clean_release.sh start.sh wiki.sh update.sh docker/entrypoint.sh 2>/dev/null || true

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV HOST=0.0.0.0
ENV TS_STATE_DIR=/var/lib/tailscale
ENV TS_SERVE_CONFIG=/config/tailscale/serve.json

EXPOSE 8080

VOLUME ["/app/data", "/app/wikis", "/app/raw", "/app/output_docs", "/var/lib/tailscale", "/config/tailscale"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/LLMWikiNG/status || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["python", "run.py", "--port", "8080", "--host", "0.0.0.0"]
