#!/bin/bash
# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
# clean_release.sh – Bereinigt die workspace-bezogenen Daten für einen sauberen Release auf GitHub.
# Schützt die Codebasis, setzt aber Nutzerdaten, temporäre Dateien und Test-Wikis zurück.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "=== 🧹 LLMWikiNG Release-Bereinigung startet ==="

echo "  • Entferne Python Cache (__pycache__, pyc)..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

echo "  • Leere raw/ Ordner..."
if [ -d "raw" ]; then
    find raw/ -type f ! -name ".gitkeep" -delete
fi

echo "  • Leere output_docs/ Ordner..."
if [ -d "output_docs" ]; then
    find output_docs/ -type f ! -name ".gitkeep" -delete
fi

echo "  • Leere backend/scratch/..."
if [ -d "backend/scratch" ]; then
    find backend/scratch/ -type f -delete
fi

echo "  • Setze Multi-Wiki-Struktur zurück..."
if [ -d "wikis" ]; then
    find wikis/ -maxdepth 1 -mindepth 1 -type d ! -name "main" -exec rm -rf {} +
    
    if [ -d "wikis/main" ]; then
        find wikis/main/ -type f ! -name "index.md" ! -name "log.md" ! -name "mcp-server-integration.md" -delete
        rm -rf wikis/main/.history 2>/dev/null || true
        
        cat > wikis/main/index.md <<EOF
---
okf_version: "0.1"
---
# LLMWikiNG (OKF Edition)

> Willkommen in deinem neuen Wiki! Dieses Wiki wurde nach dem Open Knowledge Format (OKF) v0.1 initialisiert.
EOF

        cat > wikis/main/log.md <<EOF
---
okf_version: "0.1"
---
# Wiki-Aktivitätslogbuch

## $(date +%Y-%m-%d)
- **Init**: Wiki-System initialisiert
EOF
    fi
fi

echo "  • Setze Benutzer-, API-Key-, MCP-Key-, Tailscale- und Audit-Datenbank zurück (data/)..."
mkdir -p data
echo "[]" > data/users.json
echo "[]" > data/api_keys.json
echo "[]" > data/mcp_keys.json
echo "[]" > data/audit_logs.json
rm -f data/tailscale.json 2>/dev/null || true
rm -rf data/sync_status ts-data ts-config 2>/dev/null || true

echo "  • Bereinige Matrix-Suchindex (data/matrix/)..."
rm -f data/matrix/*.db data/matrix/*.db-wal data/matrix/*.db-shm 2>/dev/null || true

echo "=== 🎉 Bereinigung abgeschlossen! Bereit für den Push auf GitHub ==="
