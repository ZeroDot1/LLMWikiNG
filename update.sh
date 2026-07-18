#!/bin/bash
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

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

die() {
    echo -e "${RED}${1}${NC}" >&2
    exit 1
}

strip_ansi() {
    sed -E 's/\x1b\[[0-9;]*[a-zA-Z]//g'
}

# ─── Start ────────────────────────────────────────────────────────────────────

# Projektverzeichnis ermitteln (dort, wo update.sh liegt)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Aktuelle Version ermitteln
CURRENT_VERSION="unbekannt"
if [ -f "VERSION" ]; then
    CURRENT_VERSION=$(cat VERSION)
fi

# Prüfen ob Git installiert ist
if ! command -v git &>/dev/null; then
    die "Git nicht gefunden. Bitte installieren: sudo pacman -S git"
fi

# Prüfen ob wir uns in einem Git-Repository befinden
if ! git rev-parse --git-dir &>/dev/null; then
    die "Kein Git-Repository gefunden. Bitte klone das Repository: git clone https://github.com/ZeroDot1/LLMWikiNG.git"
fi

# Token-Authentifizierung für private Repositories einrichten
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

# ─── --check-Modus: Nur prüfen, ob ein Update verfügbar ist ───────────────────

if [ "${1:-}" = "--check" ]; then
    echo ""
    echo -e "  Pruefe auf Updates..."

    # Remote-Version aus dem VERSION-File des main-Branches holen
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

# ─── Update ausführen ────────────────────────────────────────────────────────

echo ""
echo "==========================================================="
echo "           LLMWikiNG - Selbstupdate (Git)"
echo "==========================================================="
echo ""
echo -e "  Projektverzeichnis: ${YELLOW}${PROJECT_DIR}${NC}"
echo -e "  Aktuelle Version:   ${YELLOW}${CURRENT_VERSION}${NC}"

# ─── Backup erstellen ─────────────────────────────────────────────────────────

echo ""
echo -e "  Erstelle Backup in ${YELLOW}${BACKUP_DIR}${NC}..."
mkdir -p "$BACKUP_DIR"

# Nur Benutzerdaten sichern – NICHT die Programmdateien (die werden via git reset ersetzt)
for item in data config.json .agy.yaml wikis raw output_docs scratch; do
    if [ -e "$item" ]; then
        cp -r "$item" "$BACKUP_DIR/" 2>/dev/null || true
    fi
done

echo -e "${GREEN}Backup erstellt${NC}"
echo ""

# ─── Git-Update ───────────────────────────────────────────────────────────────

echo -e "  Hole neueste Aenderungen von GitHub..."

# Lokale Aenderungen an Benutzerdateien stashen (data/, config.json, .agy.yaml)
# Nur stashen wenn es tatsaechlich Aenderungen gibt
STASHED=0
if ! git diff --quiet -- data config.json .agy.yaml 2>/dev/null || \
   ! git diff --cached --quiet -- data config.json .agy.yaml 2>/dev/null; then
    echo -e "  -> Lokale Aenderungen an Benutzerdateien werden gestashed..."
    git stash push -m "Auto-Stash vor Update $(date '+%Y-%m-%d %H:%M:%S')" -- data config.json .agy.yaml 2>/dev/null && STASHED=1 || true
fi

# Fetch vom Remote
if ! git fetch origin 2>&1; then
    die "Git fetch fehlgeschlagen. Bitte Netzwerk pruefen."
fi

# Neueste Version auslesen
NEW_VERSION=$(git show origin/main:VERSION 2>/dev/null || echo "unbekannt")

echo -e "  Neue Version:       ${YELLOW}${NEW_VERSION}${NC}"

# Reset auf den aktuellsten Stand
echo ""
echo -e "  Aktualisiere Dateien..."

# Fuehre den Reset aus – Benutzerdaten sind im Backup geschuetzt
git reset --hard origin/main

# ─── Abhaengigkeiten installieren ─────────────────────────────────────────────

echo ""
echo -e "  Pruefe Python-Abhaengigkeiten..."

PIP_OK=0
if command -v pip3 &>/dev/null; then
    if [ -f "requirements.txt" ]; then
        echo -e "  Installiere/fuer update-requirements..."
        pip3 install --user -r requirements.txt 2>&1 | tail -3 && PIP_OK=1 || PIP_OK=0
    fi
elif command -v pip &>/dev/null; then
    if [ -f "requirements.txt" ]; then
        echo -e "  Installiere/fuer update-requirements..."
        pip install --user -r requirements.txt 2>&1 | tail -3 && PIP_OK=1 || PIP_OK=0
    fi
fi

if [ "$PIP_OK" -eq 1 ]; then
    echo -e "${GREEN}Abhaengigkeiten aktualisiert${NC}"
else
    echo -e "${YELLOW}pip nicht gefunden oderrequirements.txt fehlt – bitte manuell installieren: pip install -r requirements.txt${NC}"
fi

# ─── Benutzerdaten wiederherstellen ──────────────────────────────────────────

# Benutzerdaten (data/) aus dem Backup wiederherstellen, falls sie veraendert/geloescht wurden
if [ -d "$BACKUP_DIR/data" ]; then
    echo -e "  -> Stellt Benutzerdatenbanken aus Backup wieder her..."
    mkdir -p data
    cp -rf "$BACKUP_DIR/data/"* data/ 2>/dev/null || true
fi
if [ -f "$BACKUP_DIR/config.json" ]; then
    echo -e "  -> Stellt config.json aus Backup wieder her..."
    cp -f "$BACKUP_DIR/config.json" config.json 2>/dev/null || true
fi
if [ -f "$BACKUP_DIR/.agy.yaml" ]; then
    echo -e "  -> Stellt .agy.yaml aus Backup wieder her..."
    cp -f "$BACKUP_DIR/.agy.yaml" .agy.yaml 2>/dev/null || true
fi

# ─── Stash wiederherstellen (falls Benutzerdateien gestashed wurden) ──────────

if [ "$STASHED" -eq 1 ]; then
    echo -e "  -> Versuche gestashte Benutzerdateien wiederherzustellen..."
    git stash pop 2>/dev/null || echo -e "${YELLOW}  Hinweis: Stash-Konflikt – manuell pruefen: git stash list${NC}"
fi

# Ausfuehrbare Berechtigungen setzen
chmod +x wiki.sh start.sh tools/*.sh update.sh clean_release.sh 2>/dev/null || true

# ─── Fertig ───────────────────────────────────────────────────────────────────

echo ""
echo "==========================================================="
echo "           Update abgeschlossen!"
echo "==========================================================="
echo ""
echo -e "  ${YELLOW}${CURRENT_VERSION}${NC} -> ${YELLOW}${NEW_VERSION}${NC}"
echo ""
echo -e "  Backup-Pfad: ${CYAN}${BACKUP_DIR}${NC}"
echo ""
echo -e "  ${YELLOW}-> Bitte starte den Webserver neu, falls er laeuft:${NC}"
echo -e "    ./start.sh"
echo ""
