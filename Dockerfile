# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
FROM python:slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    iptables \
    iproute2 \
    git \
    ripgrep \
    jq \
    sqlite3 \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app


COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -r requirements.txt \
    && rm -rf /var/lib/apt/lists/*


COPY . .

RUN mkdir -p data/matrix data raw output_docs wikis/main /var/lib/tailscale /config/tailscale

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
