#!/bin/bash
# tools/qmd_search.sh
# Nutzt qmd für hybride Suche (BM25 + Vektor) und gibt JSON zurück
# Spart Tokens, indem nur Snippets statt ganzer Dateien geliefert werden
#
# Usage: ./tools/qmd_search.sh "Suchbegriff"
#        ./tools/qmd_search.sh "Suchbegriff" -n 5  (für mehr Ergebnisse)

QUERY=$1
LIMIT=${2:-3}

if [ -z "$QUERY" ]; then
    echo '{"error": "Kein Suchbegriff angegeben. Usage: qmd_search.sh \"Suchbegriff\""}'
    exit 1
fi

qmd query "$QUERY" -n "$LIMIT" --json --collection "my_wiki"
