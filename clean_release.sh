#!/bin/bash
# clean_release.sh – Bereinigt die workspace-bezogenen Daten für einen sauberen Release auf GitHub.
# Schützt die Codebasis, setzt aber Nutzerdaten, temporäre Dateien und Test-Wikis zurück.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "=== 🧹 LLMWikiNG Release-Bereinigung startet ==="

# 1. Python Cache entfernen
echo "  • Entferne Python Cache (__pycache__, pyc)..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# 2. Ingestierte Rohquellen und Exporte bereinigen
echo "  • Leere raw/ Ordner..."
if [ -d "raw" ]; then
    find raw/ -type f ! -name ".gitkeep" -delete
fi

echo "  • Leere output_docs/ Ordner..."
if [ -d "output_docs" ]; then
    find output_docs/ -type f ! -name ".gitkeep" -delete
fi

# 3. Temporäre Scratch-Dateien löschen
echo "  • Leere backend/scratch/..."
if [ -d "backend/scratch" ]; then
    find backend/scratch/ -type f -delete
fi

# 4. Wikis zurücksetzen (Nur Standard 'main' mit OKF-Templates behalten)
echo "  • Setze Multi-Wiki-Struktur zurück..."
if [ -d "wikis" ]; then
    # Lösche alle Wikis außer 'main'
    find wikis/ -maxdepth 1 -mindepth 1 -type d ! -name "main" -exec rm -rf {} +
    
    # Setze 'main' Wiki auf OKF-Standard zurück
    if [ -d "wikis/main" ]; then
        find wikis/main/ -type f ! -name "index.md" ! -name "log.md" -delete
        
        # Standard index.md neu anlegen
        cat > wikis/main/index.md <<EOF
---
okf_version: "0.1"
---
# LLMWikiNG (OKF Edition)

> Willkommen in deinem neuen Wiki! Dieses Wiki wurde nach dem Open Knowledge Format (OKF) v0.1 initialisiert.
EOF

        # Standard log.md neu anlegen
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

# 5. Benutzer- und Key-Datenbanken zurücksetzen (Erster Login Trigger beim nächsten Start)
echo "  • Setze Benutzer- und API-Key-Datenbank zurück (data/)..."
mkdir -p data
echo "[]" > data/users.json
echo "[]" > data/api_keys.json

# 6. Suchindex (qmd) zurücksetzen
echo "  • Bereinige qmd-Suchindex..."
if command -v qmd &>/dev/null; then
    qmd collection remove my_wiki 2>/dev/null || true
    qmd collection remove wiki_main 2>/dev/null || true
    qmd collection remove wiki_test 2>/dev/null || true
fi

echo "=== 🎉 Bereinigung abgeschlossen! Bereit für den Push auf GitHub ==="
