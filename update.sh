#!/bin/bash
# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
# update.sh – LLMWikiNG Update-Skript (Git-basiert)
# Holt die neueste Version via Git von GitHub und aktualisiert alle Programmdateien.
# Benutzerdaten (wikis/, raw/, output_docs/, config.json, data/, .agy.yaml) bleiben erhalten.
#
# Nutzung: ./update.sh            – Update ausführen
#          ./update.sh --check    – Nur prüfen, ob Update verfügbar ist
#
# Repository: https://github.com/ZeroDot1/LLMWikiNG

set -euo pipefail

BACKUP_DIR="/tmp/llmwiking-backup-$(date +%Y%m%d-%H%M%S)"

# Farben
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

die() {
    echo -e "${RED}${1}${NC}" >&2
    exit 1
}

strip_ansi() {
    sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g'
}

# Prueft, ob alle in requirements.txt gelisteten Python-Pakete importierbar sind.
# Liefert 0, wenn alles vorhanden ist, sonst 1 und listet die fehlenden Module.
verify_python_deps() {
    local req_file="$1"
    local py_cmd=""
    if command -v python3 &>/dev/null; then
        py_cmd="python3"
    elif command -v python &>/dev/null; then
        py_cmd="python"
    fi
    [ -z "$py_cmd" ] && return 1

    local mods="" missing="" pkg mod
    while IFS= read -r line; do
        line="${line%%#*}"                       # Inline-Kommentar entfernen
        line="$(echo "$line" | tr -d '[:space:]')"
        [ -z "$line" ] && continue
        case "$line" in
            -*) continue ;;                      # z. B. "-e git+..."
            git+*) continue ;;
            http*) continue ;;
        esac
        pkg="${line%%[<>=~!;]*}"                 # Versionsangaben/Env-Marker entfernen
        pkg="${pkg%%\[*}"                        # Extras entfernen (uvicorn[standard])
        pkg="$(echo "$pkg" | tr '[:upper:]' '[:lower:]' | tr '-' '_')"
        [ -z "$pkg" ] && continue
        case "$pkg" in
            pyyaml) mod="yaml" ;;
            python_multipart) mod="multipart" ;;
            argon2_cffi) mod="argon2" ;;
            python_frontmatter) mod="frontmatter" ;;
            *) mod="$pkg" ;;
        esac
        [ -z "$mod" ] && continue
        if [ -z "$mods" ]; then
            mods="$mod"
        else
            mods="$mods,$mod"
        fi
    done < "$req_file"

    [ -z "$mods" ] && return 0

    if "$py_cmd" -c "import $mods" >/dev/null 2>&1; then
        return 0
    fi
    local oldifs="$IFS"
    IFS=','
    local m
    for m in $mods; do
        if ! "$py_cmd" -c "import $m" >/dev/null 2>&1; then
            missing="$missing $m"
        fi
    done
    IFS="$oldifs"
    echo -e "    ${RED}Fehlende Python-Module:${NC}${missing}"
    return 1
}

# Projektverzeichnis ermitteln (dort, wo update.sh liegt)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Persistente Update-Logdatei. data/ wird in Docker-Containern als Volume
# gemountet und existiert bei allen (auch bestehenden) Installationen.
# Die Logdatei wird NIE geloescht, damit Fehler nach einem Update nachvollziehbar bleiben.
LOG_FILE="$PROJECT_DIR/data/update.log"
mkdir -p "$PROJECT_DIR/data"
# Gesamten Output (stdout+stderr) parallel in die Logdatei schreiben.
exec > >(tee "$LOG_FILE") 2>&1

# Container-Erkennung (fuer die korrekte pip-Installation im Docker-Container)
IN_CONTAINER=0
if [ -f "/.dockerenv" ] || [ -f "/run/.containerenv" ]; then
    IN_CONTAINER=1
elif grep -qE '/(docker|lxc|containerd)/' /proc/1/cgroup 2>/dev/null; then
    IN_CONTAINER=1
fi

CURRENT_VERSION="unbekannt"
if [ -f "VERSION" ]; then
    CURRENT_VERSION=$(cat VERSION)
fi

if ! command -v git &>/dev/null; then
    die "Git nicht gefunden. Bitte installieren: sudo pacman -S git"
fi

if ! git rev-parse --git-dir &>/dev/null; then
    echo -e "  ${YELLOW}Kein Git-Repository im Ordner gefunden – initialisiere Git automatisiert...${NC}"
    git init >/dev/null 2>&1 || true
    git remote add origin https://github.com/ZeroDot1/LLMWikiNG.git 2>/dev/null || git remote set-url origin https://github.com/ZeroDot1/LLMWikiNG.git 2>/dev/null || true
fi

if [ -n "${GITHUB_TOKEN:-}" ]; then
    ORIGINAL_URL=$(git remote get-url origin)
    CLEAN_URL=$(echo "$ORIGINAL_URL" | sed -E "s|https://[^@]+@|https://|")
    AUTH_URL=$(echo "$CLEAN_URL" | sed -E "s|https://|https://${GITHUB_TOKEN}@|")
    git remote set-url origin "$AUTH_URL"
fi

REMOTE_URL=$(git remote get-url origin)
# Token in der Terminalausgabe maskieren
MASKED_URL=$(echo "$REMOTE_URL" | sed -E "s|https://[^@]+@|https://***@|")
echo -e "  Remote: ${YELLOW}${MASKED_URL}${NC}"
echo -e "  Aktuelle Version: ${YELLOW}${CURRENT_VERSION}${NC}"

if [ "${1:-}" = "--check" ]; then
    echo ""
    echo -e "  Pruefe auf Updates..."

    REMOTE_VERSION=$(git fetch origin 2>&1 && git show origin/main:VERSION 2>/dev/null || echo "unbekannt")

    if [ "$REMOTE_VERSION" = "unbekannt" ] || [ -z "$REMOTE_VERSION" ]; then
        echo -e "${RED}Konnte Version von GitHub nicht abrufen.${NC}"
        exit 2
    fi

    echo -e "  GitHub Version:   ${YELLOW}${REMOTE_VERSION}${NC}"
    echo ""

    if [ "$CURRENT_VERSION" = "$REMOTE_VERSION" ]; then
        echo -e "${GREEN}LLMWikiNG ist aktuell (${CURRENT_VERSION}).${NC}"
        exit 0
    else
        echo -e "${YELLOW}Update verfuegbar: ${CURRENT_VERSION} -> ${REMOTE_VERSION}${NC}"
        exit 1
    fi
fi

echo ""
echo "==========================================================="
echo "           LLMWikiNG - Selbstupdate (Git)"
echo "==========================================================="
echo ""
echo -e "  Projektverzeichnis: ${YELLOW}${PROJECT_DIR}${NC}"
echo -e "  Aktuelle Version:   ${YELLOW}${CURRENT_VERSION}${NC}"

echo ""
echo -e "  Erstelle Backup in ${YELLOW}${BACKUP_DIR}${NC}..."
mkdir -p "$BACKUP_DIR"

# Nur Benutzerdaten sichern – NICHT die Programmdateien (die werden via git reset ersetzt)
for item in data config.json .agy.yaml wikis wiki raw output_docs scratch wiki.sh; do
    if [ -e "$item" ]; then
        cp -r "$item" "$BACKUP_DIR/" 2>/dev/null || true
    fi
done

echo -e "${GREEN}Backup erstellt${NC}"
echo ""

echo -e "  Hole neueste Aenderungen von GitHub..."

# Lokale Aenderungen an Benutzerdateien stashen (data/, config.json, .agy.yaml)
# Nur stashen wenn es tatsaechlich Aenderungen gibt
STASHED=0
# Alle lokalen Aenderungen sichern (nicht nur ausgewaehlte Dateien)
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    echo -e "  -> Lokale Aenderungen werden gestashed..."
    git stash push -m "Auto-Stash vor Update $(date '+%Y-%m-%d %H:%M:%S')" 2>/dev/null && STASHED=1 || true
fi

if ! git fetch origin 2>&1; then
    die "Git fetch fehlgeschlagen. Bitte Netzwerk pruefen."
fi

NEW_VERSION=$(git show origin/main:VERSION 2>/dev/null || echo "unbekannt")

echo -e "  Neue Version:       ${YELLOW}${NEW_VERSION}${NC}"

echo ""
echo -e "  Aktualisiere Dateien..."

# Fuehre den Reset aus – Benutzerdaten sind im Backup geschuetzt
git reset --hard origin/main

echo ""
echo -e "  Pruefe Python-Abhaengigkeiten..."

PIP_CMD=""
if command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
elif command -v pip &>/dev/null; then
    PIP_CMD="pip"
fi

MISSING_DEP=0
if [ -f "requirements.txt" ]; then
    if [ -n "$PIP_CMD" ]; then
        if [ "$IN_CONTAINER" -eq 1 ]; then
            # Docker-Container: fehlende Pakete systemweit installieren. Der
            # Container laeuft als root, damit landen Pakete in den Site-Packages
            # und sind sofort importierbar. Bereits installierte Pakete werden
            # von pip uebersprungen – funktioniert dadurch auch fuer bestehende
            # Installationen (neue Pakete in requirements.txt werden nachgezogen).
            echo -e "  Docker-Container erkannt – installiere fehlende Pakete systemweit (${CYAN}$PIP_CMD install -r requirements.txt${NC})..."
            "$PIP_CMD" install --no-cache-dir --upgrade pip setuptools 2>&1 | tail -3 || true
            if "$PIP_CMD" install --no-cache-dir -r requirements.txt 2>&1; then
                echo -e "${GREEN}Abhaengigkeiten aktualisiert${NC}"
            else
                echo -e "${RED}FEHLER: pip install -r requirements.txt fehlgeschlagen.${NC}"
                MISSING_DEP=1
            fi
        else
            echo -e "  Installiere Python-Abhaengigkeiten aus requirements.txt..."
            if "$PIP_CMD" install --user -r requirements.txt 2>&1 | tail -3; then
                echo -e "${GREEN}Abhaengigkeiten aktualisiert${NC}"
            else
                echo -e "${YELLOW}pip install fehlgeschlagen – bitte manuell: pip install -r requirements.txt${NC}"
                MISSING_DEP=1
            fi
        fi
    else
        echo -e "${YELLOW}pip nicht gefunden – pruefe Installation direkt...${NC}"
    fi

    # Verifikation: alle benoetigten Pakete wirklich importierbar?
    if [ "$MISSING_DEP" -eq 0 ]; then
        if verify_python_deps "requirements.txt"; then
            echo -e "${GREEN}Alle Python-Abhaengigkeiten sind installiert.${NC}"
        else
            echo -e "${RED}FEHLER: Fehlende Python-Pakete erkannt.${NC}"
            MISSING_DEP=1
        fi
    fi
else
    echo -e "${YELLOW}requirements.txt fehlt – bitte manuell installieren: pip install -r requirements.txt${NC}"
    MISSING_DEP=1
fi

if [ -d "$BACKUP_DIR/data" ]; then
    echo -e "  -> Stellt Benutzerdatenbanken aus Backup wieder her..."
    mkdir -p data
    cp -rf "$BACKUP_DIR/data/"* data/ 2>/dev/null || true
fi
if [ -d "$BACKUP_DIR/wikis" ]; then
    echo -e "  -> Stellt Wiki-Inhalte (wikis/) aus Backup wieder her..."
    mkdir -p wikis
    cp -rf "$BACKUP_DIR/wikis/"* wikis/ 2>/dev/null || true
fi
if [ -d "$BACKUP_DIR/raw" ]; then
    echo -e "  -> Stellt Rohquellen (raw/) aus Backup wieder her..."
    mkdir -p raw
    cp -rf "$BACKUP_DIR/raw/"* raw/ 2>/dev/null || true
fi
if [ -d "$BACKUP_DIR/output_docs" ]; then
    echo -e "  -> Stellt Exporte (output_docs/) aus Backup wieder her..."
    mkdir -p output_docs
    cp -rf "$BACKUP_DIR/output_docs/"* output_docs/ 2>/dev/null || true
fi
if [ -d "$BACKUP_DIR/scratch" ]; then
    echo -e "  -> Stellt Arbeitsdateien (scratch/) aus Backup wieder her..."
    mkdir -p scratch
    cp -rf "$BACKUP_DIR/scratch/"* scratch/ 2>/dev/null || true
fi
if [ -f "$BACKUP_DIR/config.json" ]; then
    echo -e "  -> Stellt config.json aus Backup wieder her..."
    cp -f "$BACKUP_DIR/config.json" config.json 2>/dev/null || true
fi
if [ -f "$BACKUP_DIR/.agy.yaml" ]; then
    echo -e "  -> Stellt .agy.yaml aus Backup wieder her..."
    cp -f "$BACKUP_DIR/.agy.yaml" .agy.yaml 2>/dev/null || true
fi

if [ "$STASHED" -eq 1 ]; then
    echo -e "  -> Versuche gestashte Benutzerdateien wiederherzustellen..."
    git stash pop 2>/dev/null || echo -e "${YELLOW}  Hinweis: Stash-Konflikt – manuell pruefen: git stash list${NC}"
fi

chmod +x wiki.sh start.sh tools/*.sh update.sh clean_release.sh 2>/dev/null || true

# Falls Python-Abhaengigkeiten fehlen, wird KEIN Neustart ausgeloest: sonst
# startet der Server mit dem neuen Code und stuerzt beim Import ab. Der alte
# (laufende) Prozess bleibt erreichbar und der Fehler ist in der Logdatei
# nachvollziehbar.
if [ "$MISSING_DEP" -eq 1 ]; then
    echo ""
    echo -e "${RED}===========================================================${NC}"
    echo -e "${RED}Update abgebrochen: Python-Abhaengigkeiten fehlen.${NC}"
    echo -e "${RED}Der Webserver wurde NICHT neu gestartet.${NC}"
    echo ""
    echo -e "${RED}  Logdatei:        ${LOG_FILE}${NC}"
    echo -e "${RED}  Manuell install: pip install -r requirements.txt${NC}"
    echo -e "${RED}  Danach starten:  ./start.sh (bzw. docker restart llmwiking_app)${NC}"
    echo -e "${RED}===========================================================${NC}"
    exit 1
fi

# WICHTIG: Nach git reset --hard liegt der NEUE Code auf der Platte, aber der
# laufende uvicorn-Prozess hat den ALTEN Code noch im Speicher. Ohne Neustart
# bleiben Bugs (z. B. Coroutine-500) trotz Update bestehen. Daher wird der
# Server hier sauber neu gestartet – sofern er erkannt wird.

echo ""
echo -e "  ${YELLOW}Starte Webserver neu, damit der neue Code aktiv wird...${NC}"

RESTART_DONE=0

# 1) Docker-Container: docker restart (Container hat restart: always / start.sh)
if [ -f "/.dockerenv" ] && command -v docker &>/dev/null; then
    CONTAINER_ID=$(cat /proc/self/cgroup 2>/dev/null | grep -oP 'docker[/-]\K[0-9a-f]{12,}' | head -1)
    if [ -n "$CONTAINER_ID" ]; then
        echo -e "  -> Docker-Container erkannt, starte neu..."
        docker restart "$CONTAINER_ID" >/dev/null 2>&1 && RESTART_DONE=1 || true
    fi
fi

# 2) uvicorn-PID-Datei (sofern start.sh/main.py eine schreibt)
if [ "$RESTART_DONE" -eq 0 ] && [ -f "$PROJECT_DIR/llmwiking.pid" ]; then
    OLD_PID=$(cat "$PROJECT_DIR/llmwiking.pid" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo -e "  -> Beende laufenden uvicorn (PID $OLD_PID)..."
        kill -TERM "$OLD_PID" 2>/dev/null || true
        sleep 2
        # Neu starten im Hintergrund (nohup, damit es das Terminal überlebt)
        if [ -f "$PROJECT_DIR/start.sh" ]; then
            ( cd "$PROJECT_DIR" && nohup ./start.sh >/dev/null 2>&1 & )
            RESTART_DONE=1
        fi
    fi
fi

# 3) Fallback: laufenden uvicorn/gunicorn-Prozess ueber den Port oder Prozessname finden
if [ "$RESTART_DONE" -eq 0 ]; then
    UVICORN_PID=$(pgrep -f "uvicorn.*main:main\|uvicorn.*app:app\|gunicorn.*main\|run.py" 2>/dev/null | head -1 || true)
    if [ -n "$UVICORN_PID" ]; then
        echo -e "  -> Beende laufenden Server-Prozess (PID $UVICORN_PID)..."
        kill -TERM "$UVICORN_PID" 2>/dev/null || true
        sleep 2
        if [ -f "$PROJECT_DIR/start.sh" ]; then
            ( cd "$PROJECT_DIR" && nohup ./start.sh >/dev/null 2>&1 & )
            RESTART_DONE=1
        fi
    fi
fi

# 4) Container-Modus: uvicorn laeuft als PID 1 (CMD python run.py).
#    Ein kill von PID 1 beendet den Container; docker-compose (restart:
#    unless-stopped) baut ihn mit dem NEUEN Code automatisch wieder auf.
if [ "$RESTART_DONE" -eq 0 ] && [ -f "/.dockerenv" ]; then
    if kill -0 1 2>/dev/null; then
        echo -e "  -> Container-Modus erkannt: beende PID 1 (uvicorn) -> Container restartet."
        # Kurze Pause, damit update.sh sauber beenden kann
        ( sleep 2; kill -TERM 1 2>/dev/null || kill -KILL 1 2>/dev/null ) &
        RESTART_DONE=1
    fi
fi

if [ "$RESTART_DONE" -eq 1 ]; then
    echo -e "${GREEN}Webserver-Neustart eingeleitet.${NC}"
else
    echo -e "${YELLOW}Kein laufender Webserver erkannt – starte ihn bei Bedarf manuell:${NC}"
    echo -e "    ./start.sh"
fi

echo ""
echo "==========================================================="
echo "           Update abgeschlossen!"
echo "==========================================================="
echo ""
echo -e "  ${YELLOW}${CURRENT_VERSION}${NC} -> ${YELLOW}${NEW_VERSION}${NC}"
echo ""
echo -e "  Backup-Pfad: ${CYAN}${BACKUP_DIR}${NC}"
echo ""
if [ "$RESTART_DONE" -eq 1 ]; then
    echo -e "  ${GREEN}Der Webserver wurde neu gestartet – der neue Code ist jetzt aktiv.${NC}"
else
    echo -e "  ${YELLOW}-> Bitte starte den Webserver neu, falls er laeuft:${NC}"
    echo -e "    ./start.sh"
fi
echo ""
