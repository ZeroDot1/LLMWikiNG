#!/bin/bash
# update.sh – LLMWikiNG Update-Skript (Git-basiert)
# Holt die neueste Version via Git von GitHub und aktualisiert alle Programmdateien.
# Benutzerdaten (wiki/, raw/, output_docs/, config.json) bleiben erhalten.
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
    die "❌ Git nicht gefunden. Bitte installieren: sudo pacman -S git"
fi

# Prüfen ob wir uns in einem Git-Repository befinden
if ! git rev-parse --git-dir &>/dev/null; then
    die "❌ Kein Git-Repository gefunden. Bitte klone das Repository: git clone https://github.com/ZeroDot1/LLMWikiNG.git"
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
    echo -e "  ${CYAN}Prüfe auf Updates...${NC}"

    # Remote-Version aus dem VERSION-File des main-Branches holen
    REMOTE_VERSION=$(git fetch origin 2>&1 && git show origin/main:VERSION 2>/dev/null || echo "unbekannt")

    if [ "$REMOTE_VERSION" = "unbekannt" ] || [ -z "$REMOTE_VERSION" ]; then
        echo -e "${RED}❌ Konnte Version von GitHub nicht abrufen.${NC}"
        exit 2
    fi

    echo -e "  GitHub Version:   ${YELLOW}${REMOTE_VERSION}${NC}"
    echo ""

    if [ "$CURRENT_VERSION" = "$REMOTE_VERSION" ]; then
        echo -e "${GREEN}✅ LLMWikiNG ist aktuell (${CURRENT_VERSION}).${NC}"
        exit 0
    else
        echo -e "${YELLOW}⬇️  Update verfügbar: ${CURRENT_VERSION} → ${REMOTE_VERSION}${NC}"
        exit 1
    fi
fi

# ─── Update ausführen ────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           LLMWikiNG – Selbstupdate (Git)            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Projektverzeichnis: ${YELLOW}${PROJECT_DIR}${NC}"
echo -e "  Aktuelle Version:   ${YELLOW}${CURRENT_VERSION}${NC}"

# ─── Backup erstellen ─────────────────────────────────────────────────────────

echo ""
echo -e "  Erstelle Backup in ${YELLOW}${BACKUP_DIR}${NC}..."
mkdir -p "$BACKUP_DIR"

# Sichert den gesamten aktuellen Daten- und Config-Stand (inklusive user/key DB) vor dem Git-Reset
for item in backend frontend lang requirements.txt run.py clean_release.sh Dockerfile docker-compose.yml wiki.sh start.sh update.sh VERSION CHANGELOG.md README.md LICENSE .gitignore .agy.yaml prompts templates static tools data config.json; do
    if [ -e "$item" ]; then
        cp -r "$item" "$BACKUP_DIR/" 2>/dev/null || true
    fi
done

echo -e "${GREEN}✓ Backup erstellt${NC}"
echo ""

# ─── Git-Update ───────────────────────────────────────────────────────────────

echo -e "  ${CYAN}Hole neueste Änderungen von GitHub...${NC}"

# Lokale Änderungen stashen (Benutzer-Configs und DBs temporär sichern)
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo -e "  ${YELLOW}→ Lokale Änderungen wurden gestashed (bei Bedarf: git stash pop)${NC}"
    git stash push --keep-index -m "Auto-Stash vor Update $(date '+%Y-%m-%d %H:%M:%S')"
fi

# Fetch vom Remote
if ! git fetch origin 2>&1; then
    die "❌ Git fetch fehlgeschlagen. Bitte Netzwerk prüfen."
fi

# Neueste Version auslesen
NEW_VERSION=$(git show origin/main:VERSION 2>/dev/null || echo "unbekannt")

echo -e "  Neue Version:       ${YELLOW}${NEW_VERSION}${NC}"

# Reset auf den aktuellsten Stand
echo ""
echo -e "  ${CYAN}Aktualisiere Dateien...${NC}"

# Führe den Reset nur für Programmdateien aus und schütze die Benutzerdaten
git reset --hard origin/main

# Benutzerdaten (data/ und config.json) aus dem Backup wiederherstellen, falls sie verändert/gelöscht wurden
if [ -d "$BACKUP_DIR/data" ]; then
    echo -e "  ${GREEN}→ Stellt Benutzerdatenbanken aus Backup wieder her...${NC}"
    mkdir -p data
    cp -rf "$BACKUP_DIR/data/"* data/ 2>/dev/null || true
fi
if [ -f "$BACKUP_DIR/config.json" ]; then
    echo -e "  ${GREEN}→ Stellt config.json aus Backup wieder her...${NC}"
    cp -f "$BACKUP_DIR/config.json" config.json 2>/dev/null || true
fi

# Ausführbare Berechtigungen setzen
chmod +x wiki.sh start.sh tools/*.sh update.sh change_secret.sh clean_release.sh 2>/dev/null || true

# ─── Fertig ───────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅ Update abgeschlossen!                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${YELLOW}${CURRENT_VERSION}${NC} → ${YELLOW}${NEW_VERSION}${NC}"
echo ""
echo -e "  Backup-Pfad: ${CYAN}${BACKUP_DIR}${NC}"
echo ""
echo -e "  ${YELLOW}→ Bitte starte den Webserver neu, falls er läuft:${NC}"
echo -e "    ./start.sh"
echo ""
