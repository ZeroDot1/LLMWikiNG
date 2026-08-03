#!/bin/bash
# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
# tools/matrix_search.sh
# Nutzt die Matrix-Volltextsuche (SQLite-FTS5-Shards) und gibt JSON zurück
# Spart Tokens, indem nur Snippets statt ganzer Dateien geliefert werden
#
# Usage: ./tools/matrix_search.sh "Suchbegriff"
#        ./tools/matrix_search.sh "Suchbegriff" 5  (für mehr Ergebnisse)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUERY=$1
LIMIT=${2:-3}

if [ -z "$QUERY" ]; then
    echo '{"error": "Kein Suchbegriff angegeben. Usage: matrix_search.sh \"Suchbegriff\""}'
    exit 1
fi

python3 -c "
import sys, json
sys.path.insert(0, '$SCRIPT_DIR/backend')
from services.search import search_wiki
res = search_wiki('''$QUERY''', wiki='all', num_results=$LIMIT)
print(json.dumps(res, ensure_ascii=False, indent=2))
"
