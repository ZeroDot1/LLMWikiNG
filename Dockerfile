# Dockerfile für LLMWikiNG
FROM python:3-slim

# Systemabhängigkeiten installieren (curl für Healthchecks, git für Updates, ripgrep/jq für CLI, xz-utils für Backup/Restore, libgomp1 für qmd, compiler für Rust/Pip)
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




# Rust temporär installieren, qmd-cli kompilieren und Rust wieder entfernen (hält das Image minimal)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && cargo install qmd-cli \
    && cp "$HOME/.cargo/bin/qmd" /usr/local/bin/qmd \
    && rm -rf "$HOME/.cargo" "$HOME/.rustup"

# Arbeitsverzeichnis festlegen
WORKDIR /app

# Abhängigkeiten kopieren
COPY requirements.txt .

# Python-C-Extensions kompilieren, pip-Pakete installieren und C-Compiler wieder deinstallieren (Image-Größe minimieren)
RUN pip install --no-cache-dir --upgrade pip setuptools cffi \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential gcc libffi-dev clang libclang-dev cmake pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*






# Den gesamten Projektcode in das Image kopieren
COPY . .

# Sicherstellen, dass die nötigen Ordner existieren
RUN mkdir -p data raw output_docs wikis/main

# Dateirechte anpassen, falls nötig (z. B. Startskripte ausführbar machen)
RUN chmod +x run.py clean_release.sh start.sh wiki.sh update.sh 2>/dev/null || true

# Umgebungsvariablen setzen
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV HOST=0.0.0.0

# Port im Container freigeben
EXPOSE 8080

# Volumes vordefinieren für automatische Erkennung in Docker-GUIs (wie Ugreen UGOS)
VOLUME ["/app/data", "/app/wikis", "/app/raw", "/app/output_docs"]

# Healthcheck einrichten
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/LLMWikiNG/status || exit 1

# Start-Kommando (FastAPI per run.py starten)
CMD ["python", "run.py", "--port", "8080", "--host", "0.0.0.0"]
