#!/bin/bash
# start.sh – LLMWikiNG Webserver-Starter
# by ZeroDot1 | Karpathy-Pattern | FastAPI + qmd
#
# Nutzung:
#   ./start.sh                  → Automatisch freier Port ab 8080
#   ./start.sh 9090             → Ab Port 9090 suchen
#   ./start.sh -d               → Debug-Modus (automatisch freier Port)
#   ./start.sh 9090 -d          → Port 9090 + Debug
#   ./start.sh --lang en        → Englisch als Startsprache
#   ./start.sh 9090 --lang de   → Port 9090 + Deutsch
#   ./start.sh --reset          → Server zurücksetzen (alle User-Daten löschen)
#   ./start.sh --reset -y       → Reset ohne Nachfrage ausführen
#   ./start.sh --help           → Hilfe

set -euo pipefail

APP_NAME="LLMWikiNG"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SCRIPT="$SCRIPT_DIR/run.py"
WANTED_PORT=""
DEBUG=""
LANG_ARG=""
RESET_MODE=""
RESET_FORCE=""

# ═══════════════════════════════════════════════════════════
# Argumente parsen
# ═══════════════════════════════════════════════════════════

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "$APP_NAME – Lokaler Wiki-Webserver"
            echo ""
            echo "Verwendung:"
            echo "  ./start.sh                      Automatisch freier Port (ab 8080)"
            echo "  ./start.sh 9090                 Ab Port 9090 suchen"
            echo "  ./start.sh -d                   Debug-Modus, automatisch freier Port"
            echo "  ./start.sh 9090 -d              Debug-Modus ab Port 9090"
            echo "  ./start.sh --lang en            Startsprache (z.B. de, en)"
            echo "  ./start.sh 9090 --lang de       Port 9090 + Deutsch"
            echo "  ./start.sh --reset              Server zurücksetzen (alle User-Daten löschen)"
            echo "  ./start.sh --reset -y           Reset ohne Nachfrage ausführen"
            echo ""
            echo "Weitere Parameter werden direkt an run.py (FastAPI/uvicorn) durchgereicht."
            echo "Der Server sucht automatisch den nächsten freien Port."
            echo "Danach im Browser: http://localhost:PORT"
            exit 0
            ;;
        --lang|-l)
            if [[ -n "${2:-}" ]]; then
                LANG_ARG="--lang $2"
                shift 2
            else
                echo "❌ --lang benötigt einen Wert (z.B. de, en)"
                exit 1
            fi
            ;;
        -d|--debug)
            DEBUG="--debug"
            shift
            ;;
        --reset)
            RESET_MODE="yes"
            shift
            # Prüfe auf direkt folgendes -y/--yes
            if [[ "${1:-}" == "-y" || "${1:-}" == "--yes" || "${1:-}" == "-yes" ]]; then
                RESET_FORCE="yes"
                shift
            fi
            ;;
        -y|--yes|-yes)
            # Kann vor oder nach --reset stehen
            RESET_FORCE="yes"
            shift
            ;;
        -*)
            echo "❌ Unbekannte Option: $1"
            echo "Verwende --help für Hilfe."
            exit 1
            ;;
        *)
            # Erstes nicht-Option-Argument = Port
            if [[ -z "$WANTED_PORT" ]]; then
                WANTED_PORT="$1"
            else
                echo "❌ Unerwartetes Argument: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

# Prüfen, ob -y/--yes vor --reset kam (z.B. ./start.sh -y --reset)
if [[ -z "$RESET_MODE" && -n "$RESET_FORCE" ]]; then
    # RESET_FORCE ohne RESET_MODE ist ungültig → ignorieren
    RESET_FORCE=""
fi

# Port default setzen falls nicht gesetzt
WANTED_PORT="${WANTED_PORT:-8080}"

if [ "${2:-}" = "-d" ] || [ "${1:-}" = "-d" ]; then
    DEBUG="--debug"
    if [ "${1:-}" = "-d" ]; then
        WANTED_PORT=8080
    fi
fi

# ═══════════════════════════════════════════════════════════════
# RESET-Funktion: Setzt den Server auf Werkseinstellungen zurück
# ═══════════════════════════════════════════════════════════════

reset_server() {
    local force="${1:-}"

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║   ⚠️   SERVER ZURÜCKSETZEN                           ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "${RED}⚠  ACHTUNG: Dieser Vorgang löscht unwiderruflich alle${NC}"
    echo "${RED}   Benutzerdaten: Wiki-Seiten, Rohquellen und Exporte!${NC}"
    echo ""

    if [[ "$force" != "yes" ]]; then
        echo -n "Bestätige mit 'RESET': "
        read -r confirm
        if [[ "$confirm" != "RESET" ]]; then
            echo "❌ Reset abgebrochen."
            exit 0
        fi
    fi

    echo ""
    echo "🔄 Lösche Wikis (wikis/) …"
    rm -rf "$SCRIPT_DIR/wikis"/*
    echo "🔄 Lösche Rohquellen (raw/) …"
    rm -rf "$SCRIPT_DIR/raw"/*
    echo "🔄 Lösche Exporte (output_docs/) …"
    rm -rf "$SCRIPT_DIR/output_docs"/*
    echo "🔄 Lösche Benutzer & API-Keys (data/) …"
    rm -rf "$SCRIPT_DIR/data"/*

    # index.md und log.md OKF-konform neu anlegen (Standard-Wiki "main")
    echo "🔄 Erstelle leeres Wiki-Grundgerüst …"
    mkdir -p "$SCRIPT_DIR/wikis/main" "$SCRIPT_DIR/raw" "$SCRIPT_DIR/output_docs" "$SCRIPT_DIR/data"

    cat > "$SCRIPT_DIR/wikis/main/index.md" <<-EOF
---
okf_version: "0.1"
---
# Wiki-Index

> Automatisch gepflegtes Inhaltsverzeichnis.
EOF

    cat > "$SCRIPT_DIR/wikis/main/log.md" <<-EOF
---
okf_version: "0.1"
---
# Wiki-Aktivitätslogbuch

## $(date +%Y-%m-%d)
- **Reset**: Wiki vollständig zurückgesetzt
EOF

    # qmd-Collection zurücksetzen falls installiert
    if command -v qmd &>/dev/null; then
        echo "🔄 Setze qmd-Suchindex zurück …"
        qmd collection remove "my_wiki" --yes 2>/dev/null || true
        qmd collection add "$SCRIPT_DIR/wiki" --name "my_wiki" 2>/dev/null || true
    fi

    echo ""
    echo "✅ Server erfolgreich zurückgesetzt!"
    echo "   Alle Benutzerdaten wurden gelöscht."
    echo "   Du kannst den Server jetzt neu starten: ./start.sh"
    exit 0
}

# --reset wurde angefordert
if [[ -n "$RESET_MODE" ]]; then
    reset_server "$RESET_FORCE"
fi

# ═══════════════════════════════════════════════════════════════
# Prüfen: Python + Flask + Markdown
# ═══════════════════════════════════════════════════════════════

if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 nicht gefunden. Bitte installieren: sudo pacman -S python"
    exit 1
fi

if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "❌ FastAPI nicht installiert. Bitte installieren: pip install -r requirements.txt"
    exit 1
fi

if ! python3 -c "import uvicorn" 2>/dev/null; then
    echo "❌ uvicorn nicht installiert. Bitte installieren: pip install -r requirements.txt"
    exit 1
fi

if ! python3 -c "import markdown" 2>/dev/null; then
    echo "❌ Python-Markdown nicht installiert. Bitte installieren: pip install markdown"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════
# Wiki-Verzeichnis prüfen / anlegen
# ═══════════════════════════════════════════════════════════════

if [ ! -d "$SCRIPT_DIR/wiki" ]; then
    echo "⚠ Wiki-Verzeichnis nicht gefunden. Starte init..."
    if [ -f "$SCRIPT_DIR/wiki.sh" ]; then
        bash "$SCRIPT_DIR/wiki.sh" init
    else
        mkdir -p "$SCRIPT_DIR/wiki" "$SCRIPT_DIR/raw" "$SCRIPT_DIR/output_docs"
        echo "📁 Leeres Wiki angelegt."
    fi
fi

# ═══════════════════════════════════════════════════════════════
# Automatisch freien Port finden
# ═══════════════════════════════════════════════════════════════

find_free_port() {
    local port="$1"
    local max_port="$((port + 99))"  # Maximal 100 Ports weit probieren

    while [ "$port" -le "$max_port" ]; do
        if command -v ss &>/dev/null; then
            if ! ss -tlnp 2>/dev/null | grep -qP ":$port "; then
                echo "$port"
                return 0
            fi
        elif command -v lsof &>/dev/null; then
            if ! lsof -i:"$port" &>/dev/null; then
                echo "$port"
                return 0
            fi
        else
            # Fallback: Einfach versuchen, eine Verbindung aufzumachen
            if ! timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/$port" 2>/dev/null; then
                echo "$port"
                return 0
            fi
        fi
        port="$((port + 1))"
    done

    echo ""  # Kein freier Port gefunden
    return 1
}

PORT=$(find_free_port "$WANTED_PORT")

if [ -z "$PORT" ]; then
    echo "❌ Kein freier Port im Bereich $WANTED_PORT–$((WANTED_PORT + 99)) gefunden."
    exit 1
fi

# Info, wenn nicht der gewünschte Port genutzt wird
if [ "$PORT" -ne "$WANTED_PORT" ]; then
    echo "⚠ Port $WANTED_PORT belegt – nutze stattdessen Port $PORT."
fi

# ═══════════════════════════════════════════════════════════════
# Server starten
# ═══════════════════════════════════════════════════════════════

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║  $APP_NAME"
echo "║  edition by ZeroDot1"
echo "║  Version $(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo '1.8.0')"
echo "╠════════════════════════════════════════════════╣"
echo "║  📂 Wikis:    $SCRIPT_DIR/wikis"
echo "║  🌐 URL:      http://localhost:${PORT}"
echo "║  🛑 Stopp:    Strg+C"
echo "╚════════════════════════════════════════════════╝"
echo ""

exec python3 "$SERVER_SCRIPT" --port "$PORT" --host "0.0.0.0" $DEBUG $LANG_ARG
