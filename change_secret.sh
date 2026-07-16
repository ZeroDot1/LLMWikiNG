#!/bin/bash
# change_secret.sh – Hilfsskript zum Generieren eines neuen LLMWikiNG-Secrets
# 
# Verhindert, dass das Standard-Geheimnis in der docker-compose.yml verbleibt.
# Generiert ein neues, zufälliges kryptografisches Secret und trägt es in die docker-compose.yml ein.

set -euo pipefail

COMPOSE_FILE="docker-compose.yml"
NC='\033[0m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   LLMWikiNG – Secret Changer / Geheimnis-Generator          ${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "Das kryptografische Geheimnis (LLMWIKI_SECRET) schützt deine"
echo "Sitzungen und verschlüsselt deine API-Schlüssel im Container."
echo "Es sollte für jede Installation einzigartig und geheim sein."
echo ""

if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}❌ Fehler: '$COMPOSE_FILE' wurde im aktuellen Verzeichnis nicht gefunden!${NC}"
    echo "Bitte führe dieses Skript im Hauptverzeichnis des Projekts aus."
    exit 1
fi

# Generiert ein sicheres 64-Zeichen Hex-Secret
NEW_SECRET=$(openssl rand -hex 32 2>/dev/null || od -vAn -N32 -tx1 /dev/urandom | tr -d '[:space:]')

if [ -z "$NEW_SECRET" ]; then
    echo -e "${RED}❌ Fehler: Es konnte kein sicheres Secret generiert werden.${NC}"
    exit 1
fi

echo -e "${YELLOW}Schreibe neues Secret in $COMPOSE_FILE...${NC}"

# Ersetzt das bestehende Secret in der docker-compose.yml (unterstützt GNU-sed und macOS-sed)
if sed --version 2>&1 | grep -q "GNU"; then
    sed -i "s/LLMWIKI_SECRET=[a-zA-Z0-9]*/LLMWIKI_SECRET=$NEW_SECRET/g" "$COMPOSE_FILE"
else
    sed -i "" "s/LLMWIKI_SECRET=[a-zA-Z0-9]*/LLMWIKI_SECRET=$NEW_SECRET/g" "$COMPOSE_FILE"
fi

echo -e "${GREEN}✅ Erfolgreich aktualisiert!${NC}"
echo ""
echo -e "Neues Secret in der Compose-Datei: ${GREEN}$NEW_SECRET${NC}"
echo ""
echo -e "${YELLOW}Wichtig:${NC} Wenn du bereits API-Schlüssel generiert hast, können diese nach"
echo "dem Ändern des Secrets nicht mehr entschlüsselt werden. Du musst diese"
echo "neu in der WebUI unter Settings -> API-Keys anlegen."
echo ""
echo "Starte den Container nun neu, um die Änderungen zu übernehmen:"
echo -e "   ${CYAN}docker compose down && docker compose up -d${NC}"
echo ""
