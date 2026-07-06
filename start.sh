#!/bin/bash
# start.sh – LLMWikiNG Webserver-Starter
# by ZeroDot1 | Karpathy-Pattern | Flask + qmd
#
# Nutzung:
#   ./start.sh                  → Automatisch freier Port ab 8080
#   ./start.sh 9090             → Ab Port 9090 suchen
#   ./start.sh -d               → Debug-Modus (automatisch freier Port)
#   ./start.sh 9090 -d          → Port 9090 + Debug
#   ./start.sh --lang en        → Englisch als Startsprache
#   ./start.sh 9090 --lang de   → Port 9090 + Deutsch
#   ./start.sh --help           → Hilfe

set -euo pipefail

APP_NAME="LLMWikiNG"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SCRIPT="$SCRIPT_DIR/llmWiki.py"
WANTED_PORT=""
DEBUG=""
LANG_ARG=""

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
            echo ""
            echo "Weitere Parameter werden direkt an llmWiki.py durchgereicht."
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

# Port default setzen falls nicht gesetzt
WANTED_PORT="${WANTED_PORT:-8080}"

if [ "${2:-}" = "-d" ] || [ "${1:-}" = "-d" ]; then
    DEBUG="--debug"
    if [ "${1:-}" = "-d" ]; then
        WANTED_PORT=8080
    fi
fi

# ═══════════════════════════════════════════════════════════════
# Prüfen: Python + Flask + Markdown
# ═══════════════════════════════════════════════════════════════

if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 nicht gefunden. Bitte installieren: sudo pacman -S python"
    exit 1
fi

if ! python3 -c "import flask" 2>/dev/null; then
    echo "❌ Flask nicht installiert. Bitte installieren: pip install flask"
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
echo "║  Version 1.1.0"
echo "╠════════════════════════════════════════════════╣"
echo "║  📂 Wiki:     $SCRIPT_DIR/wiki"
echo "║  🌐 URL:      http://localhost:${PORT}"
echo "║  🛑 Stopp:    Strg+C"
echo "╚════════════════════════════════════════════════╝"
echo ""

exec python3 "$SERVER_SCRIPT" --port "$PORT" --host "0.0.0.0" $DEBUG $LANG_ARG
