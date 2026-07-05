#!/bin/bash
# update.sh – LLMWikiNG Update-Skript
# Lädt die neueste Version von GitHub herunter und ersetzt alle Programmdateien.
# Benutzerdaten (wiki/, raw/, output_docs/, config.json) bleiben erhalten.
#
# Nutzung: ./update.sh            – Update ausführen
#          ./update.sh --check    – Nur prüfen, ob Update verfügbar ist
#
# Repository: https://github.com/ZeroDot1/LLMWikiNG

set -euo pipefail

REPO_URL="https://github.com/ZeroDot1/LLMWikiNG"
TEMP_DIR="/tmp/llmwiking-update-$$"
BACKUP_DIR="/tmp/llmwiking-backup-$(date +%Y%m%d-%H%M%S)"

# Farben
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

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

# Prüfen ob curl installiert ist
if ! command -v curl &>/dev/null; then
    die "❌ curl nicht gefunden. Bitte installieren: sudo pacman -S curl"
fi

# ─── --check-Modus: Nur prüfen, ob ein Update verfügbar ist ───────────────────

if [ "${1:-}" = "--check" ]; then
    echo -e "  Aktuelle Version: ${YELLOW}${CURRENT_VERSION}${NC}"
    GITHUB_VERSION=$(curl -sL "https://raw.githubusercontent.com/ZeroDot1/LLMWikiNG/main/VERSION" 2>/dev/null || echo "unbekannt")
    echo -e "  GitHub Version:   ${YELLOW}${GITHUB_VERSION}${NC}"
    echo ""
    if [ "$GITHUB_VERSION" = "unbekannt" ] || [ -z "$GITHUB_VERSION" ]; then
        echo -e "${RED}❌ Konnte Version von GitHub nicht abrufen.${NC}"
        exit 2
    fi
    if [ "$CURRENT_VERSION" = "$GITHUB_VERSION" ]; then
        echo -e "${GREEN}✅ LLMWikiNG ist aktuell (${CURRENT_VERSION}).${NC}"
        exit 0
    else
        echo -e "${YELLOW}⬇️  Update verfügbar: ${CURRENT_VERSION} → ${GITHUB_VERSION}${NC}"
        exit 1
    fi
fi

echo -e "${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           LLMWikiNG – Selbstupdate                  ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Projektverzeichnis: ${YELLOW}$PROJECT_DIR${NC}"
echo -e "  Aktuelle Version:   ${YELLOW}${CURRENT_VERSION}${NC}"

# Prüfen ob unzip installiert ist
if ! command -v unzip &>/dev/null; then
    die "❌ unzip nicht gefunden. Bitte installieren: sudo pacman -S unzip"
fi

echo ""

# ─── Download ─────────────────────────────────────────────────────────────────

DOWNLOAD_URL="${REPO_URL}/archive/refs/heads/main.zip"
echo -e "  Lade neueste Version von GitHub..."
echo -e "  ${YELLOW}${DOWNLOAD_URL}${NC}"

mkdir -p "$TEMP_DIR"
HTTP_CODE=$(curl -sL -w "%{http_code}" "$DOWNLOAD_URL" -o "$TEMP_DIR/repo.zip")

if [ "$HTTP_CODE" != "200" ] || [ ! -s "$TEMP_DIR/repo.zip" ]; then
    die "❌ Download fehlgeschlagen (HTTP $HTTP_CODE)."
fi

# ZIP-Größe prüfen
ZIP_SIZE=$(stat -c%s "$TEMP_DIR/repo.zip" 2>/dev/null || stat -f%z "$TEMP_DIR/repo.zip" 2>/dev/null)
if [ "$ZIP_SIZE" -lt 1000 ]; then
    die "❌ Heruntergeladene Datei ist zu klein ($ZIP_SIZE Bytes) – vermutlich Fehler."
fi

echo -e "${GREEN}✓ Download erfolgreich (${ZIP_SIZE} Bytes)${NC}"

# ─── Entpacken ────────────────────────────────────────────────────────────────

echo -e "  Entpacke..."
unzip -q "$TEMP_DIR/repo.zip" -d "$TEMP_DIR"

EXTRACTED_DIR="$TEMP_DIR/LLMWikiNG-main"
if [ ! -d "$EXTRACTED_DIR" ]; then
    # Fallback: falls der Branch-Name anders ist
    EXTRACTED_DIR=$(find "$TEMP_DIR" -maxdepth 2 -type d -name "LLMWikiNG-*" | head -1)
fi

if [ ! -d "$EXTRACTED_DIR" ]; then
    die "❌ Entpacken fehlgeschlagen – Verzeichnis nicht gefunden."
fi

echo -e "${GREEN}✓ Entpackt nach ${EXTRACTED_DIR}${NC}"

# Neue Version auslesen
NEW_VERSION="unbekannt"
if [ -f "$EXTRACTED_DIR/VERSION" ]; then
    NEW_VERSION=$(cat "$EXTRACTED_DIR/VERSION")
fi
echo -e "  Neue Version:       ${YELLOW}${NEW_VERSION}${NC}"

# ─── Backup erstellen ─────────────────────────────────────────────────────────

echo ""
echo -e "  Erstelle Backup in ${YELLOW}${BACKUP_DIR}${NC}..."
mkdir -p "$BACKUP_DIR"

# Nur Programmdateien und Konfiguration sichern (nicht wiki/, raw/, output_docs/)
for item in wiki.sh llmWiki.py email_sender.py start.sh update.sh VERSION CHANGELOG.md README.md LICENSE .gitignore .agy.yaml prompts templates static tools; do
    if [ -e "$item" ]; then
        cp -r "$item" "$BACKUP_DIR/" 2>/dev/null || true
    fi
done

echo -e "${GREEN}✓ Backup erstellt${NC}"

# ─── Programmdateien ersetzen ─────────────────────────────────────────────────

echo ""
echo -e "  Aktualisiere Programmdateien..."
echo ""

# Verzeichnisse, die ersetzt werden (rekursiv)
REPLACE_DIRS=(
    "prompts"
    "templates"
    "static"
    "tools"
)

# Dateien, die ersetzt werden
REPLACE_FILES=(
    "wiki.sh"
    "llmWiki.py"
    "email_sender.py"
    "start.sh"
    "update.sh"
    "VERSION"
    "CHANGELOG.md"
    "README.md"
    "LICENSE"
    ".gitignore"
)

# Verzeichnisse ersetzen
for dir in "${REPLACE_DIRS[@]}"; do
    SOURCE="$EXTRACTED_DIR/$dir"
    if [ -d "$SOURCE" ]; then
        rm -rf "./$dir"
        cp -r "$SOURCE" "./$dir"
        echo -e "  ${GREEN}✓${NC} $dir/"
    fi
done

# Dateien ersetzen
for file in "${REPLACE_FILES[@]}"; do
    SOURCE="$EXTRACTED_DIR/$file"
    if [ -f "$SOURCE" ]; then
        cp -f "$SOURCE" "./$file"
        echo -e "  ${GREEN}✓${NC} $file"
    fi
done

# .agy.yaml: Nur ersetzen, wenn die Konfiguration neu ist und noch keine
# benutzerdefinierten Einstellungen enthält. Sonst: prompts/system.md separat.
# Die .agy.yaml des Users bleibt erhalten (LLM-Modell, Temperatur etc.).
if [ -f "$EXTRACTED_DIR/.agy.yaml" ] && [ ! -f ".agy.yaml.user" ]; then
    # Backup der alten .agy.yaml
    cp -f ".agy.yaml" "$BACKUP_DIR/.agy.yaml" 2>/dev/null || true
fi

# Ausführbare Berechtigungen setzen
chmod +x wiki.sh start.sh tools/*.sh update.sh 2>/dev/null || true

# ─── Nicht ersetzte Benutzerdaten (zur Sicherheit nochmal auflisten) ──────────

echo ""
echo -e "  ${GREEN}✓${NC} Benutzerdaten bleiben erhalten:"
echo -e "     • config.json     (SMTP-Konfiguration)"
echo -e "     • .agy.yaml       (LLM-Modell-Einstellungen)"
echo -e "     • wiki/           (Wiki-Seiten)"
echo -e "     • raw/            (Rohquellen)"
echo -e "     • output_docs/    (Exporte)"

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
