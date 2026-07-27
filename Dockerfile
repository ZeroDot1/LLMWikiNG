FROM python:3-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
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
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && cargo install qmd-cli \
    && cp "$HOME/.cargo/bin/qmd" /usr/local/bin/qmd \
    && rm -rf "$HOME/.cargo" "$HOME/.rustup"

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools cffi \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential gcc libffi-dev clang libclang-dev cmake pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN mkdir -p data raw output_docs wikis/main

RUN chmod +x run.py clean_release.sh start.sh wiki.sh update.sh 2>/dev/null || true

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV HOST=0.0.0.0

EXPOSE 8080

VOLUME ["/app/data", "/app/wikis", "/app/raw", "/app/output_docs"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/LLMWikiNG/status || exit 1

CMD ["python", "run.py", "--port", "8080", "--host", "0.0.0.0"]
