#!/bin/bash
# tools/read_and_export.sh
# Liest eine Wiki-Datei UND exportiert sie automatisch in output_docs/
#
# Usage: ./tools/read_and_export.sh <dateipfad>
#        ./tools/read_and_export.sh wiki/arch_install.md

FILE_PATH=$1
EXPORT_DIR="./output_docs"
WIKI_BASE="./wiki"

if [ -z "$FILE_PATH" ]; then
    echo "Fehler: Kein Dateipfad angegeben. Usage: read_and_export.sh <dateipfad>"
    exit 1
fi

# Auflösung: Wenn nur ein Name ohne Pfad übergeben wird, in wiki/ suchen
if [[ "$FILE_PATH" != *"/"* ]]; then
    RESOLVED="$WIKI_BASE/$FILE_PATH"
else
    RESOLVED="$FILE_PATH"
fi

# Sicherheitscheck: Existiert die Datei?
if [ ! -f "$RESOLVED" ]; then
    echo "Fehler: Datei '$RESOLVED' nicht gefunden."
    echo "Vorhandene Wiki-Dateien:"
    find "$WIKI_BASE" -name "*.md" 2>/dev/null | head -20
    exit 1
fi

# Dateinamen extrahieren
FILENAME=$(basename "$RESOLVED")
DEST="$EXPORT_DIR/$FILENAME"

# Ausgabe für den LLM-Agenten (maschinenlesbar)
echo "--- SYSTEM INFO ---"
echo "QUELLE: $RESOLVED"
echo "EXPORT: $DEST"

# 1. Datei in den Export-Ordner kopieren
cp "$RESOLVED" "$DEST"
echo "STATUS: ✅ Erfolgreich nach $DEST kopiert"
echo "--- INHALT START ---"

# 2. Inhalt ausgeben (für den Agenten)
cat "$RESOLVED"

echo "--- INHALT ENDE ---"
