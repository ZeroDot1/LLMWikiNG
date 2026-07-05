#!/bin/bash
# wiki.sh – Vollständiges All-in-One CLI für das LLM Wiki (Karpathy-Pattern)
# Integration: qmd-Suche, Ingest, Export, Lint, Ollama/agy/opencode
#
# Nutzung: ./wiki.sh [befehl] [parameter]
#
# Befehle:
#   init                – Ordner anlegen + qmd-Collection initialisieren
#   sync                – qmd-Embeddings aktualisieren
#   search "text"       – Token-sparende Hybrid-Suche via qmd (JSON)
#   export <datei>      – Datei lesen + nach output_docs/ exportieren
#   list                – Alle Wiki-Dokumente anzeigen
#   ingest <quelldatei> – Neue Quelle einspielen (kopiert nach raw/, fasst zusammen, updatet Index + Log)
#   lint                – Wiki-Gesundheitscheck (orphane Seiten, Querverweise, Statistik)
#   status              – Wiki-Statistiken anzeigen
#   config              – Aktuelle Konfiguration anzeigen
#   help                – Diese Hilfe

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# KONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
WIKI_DIR="./wiki"
RAW_DIR="./raw"
EXPORT_DIR="./output_docs"
COLLECTION_NAME="my_wiki"

# LLM-Backend (erkannt: ollama, agy, opencode)
# Für Ingest-Zusammenfassungen / Lint-Analysen
LLM_BACKEND="${LLM_BACKEND:-ollama}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"

# ═══════════════════════════════════════════════════════════════════════════════
# FARBEN
# ═══════════════════════════════════════════════════════════════════════════════
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ═══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ═══════════════════════════════════════════════════════════════════════════════

# Datum im ISO-Format
today()    { date +%Y-%m-%d; }
now_iso()  { date +%Y-%m-%dT%H:%M:%S; }

# Prüft ob ein Befehl existiert
check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo -e "${RED}❌ '$1' nicht gefunden. Bitte installieren: $2${NC}"
        return 1
    fi
}

# Slug aus Titel generieren (für Dateinamen)
slugify() {
    echo "$1" \
        | sed 's/[/@#!$%^&*()]//g' \
        | tr '[:upper:]' '[:lower:]' \
        | sed 's/[ä]/ae/g; s/[ö]/oe/g; s/[ü]/ue/g; s/[ß]/ss/g' \
        | sed 's/[^a-z0-9]/-/g' \
        | sed 's/--*/-/g; s/^-//; s/-$//'
}

# Dateiname aus Quellpfad extrahieren (ohne Erweiterung)
basename_noext() {
    local f=$(basename "$1")
    echo "${f%.*}"
}

# ─── LLM-Unterstützung (ollama/agy) ──────────────────────────────────────────
llm_available() {
    case "$LLM_BACKEND" in
        ollama)  command -v ollama &>/dev/null && ollama list &>/dev/null ;;
        agy)     command -v agy &>/dev/null ;;
        opencode) command -v opencode &>/dev/null ;;
        *)       return 1 ;;
    esac
}

llm_summarize() {
    local text="$1"
    local title="${2:-Unbekannte Quelle}"

    case "$LLM_BACKEND" in
        ollama)
            if command -v ollama &>/dev/null; then
                ollama run "$OLLAMA_MODEL" \
                    "Fasse den folgenden Text auf Deutsch kurz und präzise zusammen (max. 5 Sätze). Gib auch 3-5 Schlüsselbegriffe als Tags an.

Titel: $title

Text:
$text" 2>/dev/null || echo "_Zusammenfassung nicht verfügbar (ollama nicht erreichbar)_"
            else
                echo "_Zusammenfassung nicht verfügbar (ollama nicht installiert)_"
            fi
            ;;
        agy|opencode)
            echo "_Zusammenfassung via $LLM_BACKEND möglich (manuell auslösbar)_"
            ;;
        *)
            echo "_Kein LLM-Backend konfiguriert_"
            ;;
    esac
}

# ─── Index updaten ────────────────────────────────────────────────────────────
update_index() {
    local idx_file="$WIKI_DIR/index.md"
    local tmp_file=$(mktemp)

    echo "# Wiki-Index" > "$tmp_file"
    echo "" >> "$tmp_file"
    echo "> Automatisch gepflegtes Inhaltsverzeichnis." >> "$tmp_file"
    echo "> Aktualisiert am $(today)." >> "$tmp_file"
    echo "" >> "$tmp_file"

    # Alle .md-Dateien ausser index.md und log.md auflisten
    local pages=$(find "$WIKI_DIR" -maxdepth 1 -name "*.md" \
        ! -name "index.md" ! -name "log.md" | sort)

    if [ -n "$pages" ]; then
        echo "## Seiten" >> "$tmp_file"
        echo "" >> "$tmp_file"
        while IFS= read -r page; do
            local name=$(basename "$page" .md)
            # Erste Überschrift als Beschreibung extrahieren (YAML-Frontmatter überspringen)
            local desc=$(sed -n '/^# /{s/^# //p;q}' "$page" 2>/dev/null || echo "$name")
            echo "- [[${name}.md]] – $desc" >> "$tmp_file"
        done <<< "$pages"
    fi

    # Kategorien / Entities (Unterordner)
    local subdirs=$(find "$WIKI_DIR" -mindepth 2 -type d 2>/dev/null | sort)
    if [ -n "$subdirs" ]; then
        echo "" >> "$tmp_file"
        echo "## Kategorien" >> "$tmp_file"
        echo "" >> "$tmp_file"
        while IFS= read -r dir; do
            local dirname=$(basename "$dir")
            local count=$(find "$dir" -name "*.md" | wc -l)
            echo "- **$dirname/** – $count Seite(n)" >> "$tmp_file"
        done <<< "$subdirs"
    fi

    # Statistik
    local total=$(find "$WIKI_DIR" -maxdepth 1 -name "*.md" ! -name "index.md" | wc -l)
    echo "" >> "$tmp_file"
    echo "## Statistik" >> "$tmp_file"
    echo "" >> "$tmp_file"
    echo "- **Seiten gesamt:** $total" >> "$tmp_file"
    echo "- **Letzte Aktualisierung:** $(today)" >> "$tmp_file"

    mv "$tmp_file" "$idx_file"
    echo -e "${GREEN}✓ index.md aktualisiert${NC}"
}

# ─── Log updaten ──────────────────────────────────────────────────────────────
append_log() {
    local action="$1"    # z. B. "ingest", "lint", "query"
    local title="$2"
    local details="${3:-}"

    local log_file="$WIKI_DIR/log.md"
    local entry="## [$(today)] $action | $title"
    [ -n "$details" ] && entry+="\n- $details"

    echo "" >> "$log_file"
    echo "$entry" >> "$log_file"
    echo -e "${GREEN}✓ log.md aktualisiert${NC}"
}

# ═══════════════════════════════════════════════════════════════════════════════
# BEFEHLE
# ═══════════════════════════════════════════════════════════════════════════════

show_help() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║      LLM-Wiki CLI – Karpathy-Pattern mit qmd        ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Verwendung:${NC} $0 [befehl] [parameter]"
    echo ""
    echo -e "${YELLOW}Kern-Befehle:${NC}"
    echo "  search \"text\"         🔍  Hybrid-Suche (BM25+Vektor). JSON-Ausgabe (token-sparend!)"
    echo "  export <datei>         📄  Datei lesen + nach $EXPORT_DIR exportieren"
    echo "  ingest <quelldatei>    📥  Neue Quelle einspielen (raw/ + wiki/ + index + log)"
    echo "  lint                   🏥  Wiki-Gesundheitscheck (orphane Seiten, Statistik)"
    echo ""
    echo -e "${YELLOW}Verwaltung:${NC}"
    echo "  init                   🚀  Ordner anlegen + qmd-Collection initialisieren"
    echo "  sync                   🔄  qmd-Embeddings aktualisieren"
    echo "  reindex                📑  index.md neu aufbauen (nach manuellen Änderungen)"
    echo "  list                   📋  Alle Wiki-Dokumente anzeigen"
    echo "  status                 📊  Wiki-Statistiken"
    echo "  config                 ⚙️   Konfiguration anzeigen"
    echo "  help                   ❓  Diese Hilfe"
    echo ""
    echo -e "${YELLOW}Beispiele:${NC}"
    echo "  $0 init"
    echo '  $0 search "Arch Linux Installation"'
    echo "  $0 export llm-wiki.md"
    echo "  $0 ingest ~/Dokumente/artikel.md"
    echo "  $0 lint"
    echo "  $0 status"
    echo ""
    echo -e "${CYAN}Umgebungsvariablen:${NC}"
    echo "  LLM_BACKEND=ollama|agy|opencode  (Standard: ollama)"
    echo "  OLLAMA_MODEL=llama3.2:3b          (Standard: llama3.2:3b)"
}

# ─── 1. INIT ──────────────────────────────────────────────────────────────────
init_wiki() {
    echo -e "${YELLOW}🚀 Initialisiere LLM-Wiki-Struktur...${NC}"

    # Alle benötigten Ordner anlegen
    mkdir -p "$WIKI_DIR" "$RAW_DIR" "$EXPORT_DIR"
    echo -e "${GREEN}✓ Ordner:${NC}"
    echo "   • $WIKI_DIR      – Wiki-Seiten"
    echo "   • $RAW_DIR       – Rohquellen (immutable)"
    echo "   • $EXPORT_DIR    – Exportierte Dokumente"

    # index.md anlegen falls nicht vorhanden
    if [ ! -f "$WIKI_DIR/index.md" ]; then
        cat > "$WIKI_DIR/index.md" <<-EOF
# Wiki-Index

> Automatisch gepflegtes Inhaltsverzeichnis.
> Aktualisiert am $(today).

## Statistik

- **Seiten gesamt:** 0
- **Letzte Aktualisierung:** $(today)
EOF
        echo -e "${GREEN}✓ index.md angelegt${NC}"
    fi

    # log.md anlegen falls nicht vorhanden
    if [ ! -f "$WIKI_DIR/log.md" ]; then
        cat > "$WIKI_DIR/log.md" <<-EOF
# Wiki-Log

> Chronologische Übersicht aller Änderungen.
> Format: \`## [YYYY-MM-DD] Aktion | Titel\`

## [$(today)] init | LLM-Wiki eingerichtet
- Initiales Setup mit wiki.sh, qmd-Integration, raw/- und output_docs/-Ordnern
EOF
        echo -e "${GREEN}✓ log.md angelegt${NC}"
    fi

    # qmd-Collection
    if qmd collection list 2>/dev/null | grep -q "$COLLECTION_NAME"; then
        echo -e "${GREEN}✓ qmd-Collection '$COLLECTION_NAME' existiert bereits${NC}"
    else
        echo -e "${YELLOW}📦 Erstelle qmd-Collection '$COLLECTION_NAME'...${NC}"
        qmd collection add "$WIKI_DIR" --name "$COLLECTION_NAME"
        echo -e "${GREEN}✓ qmd-Collection angelegt${NC}"
    fi

    # LLM-Backend prüfen
    echo -e "${YELLOW}🔍 Prüfe LLM-Backend...${NC}"
    case "$LLM_BACKEND" in
        ollama)
            if command -v ollama &>/dev/null; then
                local models=$(ollama list 2>/dev/null | head -5 || true)
                echo -e "${GREEN}✓ ollama verfügbar${NC}"
                if [ -n "$models" ]; then
                    echo "   Modelle:"
                    echo "$models" | tail -n +2 | while read -r line; do
                        echo "   • $line"
                    done
                fi
            else
                echo -e "${YELLOW}⚠ ollama nicht installiert (optional für KI-Zusammenfassungen)${NC}"
            fi
            ;;
        agy)
            command -v agy &>/dev/null && echo -e "${GREEN}✓ agy verfügbar${NC}" \
                || echo -e "${YELLOW}⚠ agy nicht gefunden${NC}"
            ;;
        opencode)
            command -v opencode &>/dev/null && echo -e "${GREEN}✓ opencode verfügbar${NC}" \
                || echo -e "${YELLOW}⚠ opencode nicht gefunden${NC}"
            ;;
    esac

    # Embeddings generieren
    sync_wiki
    echo -e "${GREEN}✅ Initialisierung abgeschlossen!${NC}"
}

# ─── 2. SYNC ──────────────────────────────────────────────────────────────────
sync_wiki() {
    echo -e "${YELLOW}🔄 Aktualisiere qmd-Embeddings...${NC}"
    if command -v qmd &>/dev/null; then
        qmd embed 2>&1 | grep -v "WARNING: radv" || true
        echo -e "${GREEN}✓ qmd-Embeddings aktualisiert${NC}"
    else
        echo -e "${RED}❌ qmd nicht installiert. 'sudo pacman -S qmd'${NC}"
        exit 1
    fi
}

# ─── 3. SEARCH ────────────────────────────────────────────────────────────────
search_wiki() {
    local QUERY=$1
    if [ -z "$QUERY" ]; then
        echo -e "${RED}❌ Fehler: Kein Suchbegriff angegeben.${NC}"
        echo "Usage: $0 search \"Suchbegriff\""
        exit 1
    fi

    # -n 3: limitiert Ergebnisse (Token sparen!)
    # --json: strukturierte Ausgabe für LLM-Agenten
    if command -v qmd &>/dev/null; then
        qmd query "$QUERY" -n 3 --json 2>&1 | grep -v "WARNING: radv" || true
    else
        echo -e "${RED}❌ qmd nicht installiert${NC}"
        exit 1
    fi
}

# ─── 4. EXPORT ────────────────────────────────────────────────────────────────
export_wiki() {
    local FILE=$1
    if [ -z "$FILE" ]; then
        echo -e "${RED}❌ Fehler: Keine Datei angegeben.${NC}"
        echo "Usage: $0 export [dateiname oder pfad]"
        exit 1
    fi

    # Pfad auflösen
    local TARGET_PATH="$FILE"
    if [ ! -f "$TARGET_PATH" ]; then
        local BASENAME=$(basename "$FILE")
        if [ -f "$WIKI_DIR/$BASENAME" ]; then
            TARGET_PATH="$WIKI_DIR/$BASENAME"
        elif [ -f "$WIKI_DIR/$FILE" ]; then
            TARGET_PATH="$WIKI_DIR/$FILE"
        fi
    fi

    if [ ! -f "$TARGET_PATH" ]; then
        echo -e "${RED}❌ Fehler: Datei '$FILE' nicht gefunden.${NC}"
        echo "Vorhandene Wiki-Dateien:"
        list_wiki
        exit 1
    fi

    local FILENAME=$(basename "$TARGET_PATH")
    local DEST="$EXPORT_DIR/$FILENAME"

    cp "$TARGET_PATH" "$DEST"

    # Ausgabe für LLM-Agenten (maschinenlesbar)
    echo "--- SYSTEM INFO: ✅ Datei erfolgreich nach $DEST kopiert ---"
    echo "--- INHALT START ---"
    cat "$TARGET_PATH"
    echo "--- INHALT ENDE ---"
}

# ─── 5. LIST ──────────────────────────────────────────────────────────────────
list_wiki() {
    local files=$(find "$WIKI_DIR" -type f -name "*.md" \
        ! -name "index.md" ! -name "log.md" \
        | sed "s|^$WIKI_DIR/||" | sort)
    local index_only=$(find "$WIKI_DIR" -maxdepth 1 -name "index.md" | wc -l)
    local log_only=$(find "$WIKI_DIR" -maxdepth 1 -name "log.md" | wc -l)

    if [ -z "$files" ]; then
        echo -e "${YELLOW}📭 Keine Inhaltsseiten im Wiki gefunden.${NC}"
        echo "   (index.md und log.md sind Verwaltungsdateien)"
    else
        echo -e "${BLUE}=== Wiki-Dokumente ===${NC}"
        echo "$files"
    fi
    echo ""
    echo -e "${CYAN}Verwaltung:${NC} index.md, log.md"
}

# ─── 6. INGEST ────────────────────────────────────────────────────────────────
ingest_wiki() {
    local SOURCE_FILE="$1"

    if [ -z "$SOURCE_FILE" ]; then
        echo -e "${RED}❌ Fehler: Keine Quelldatei angegeben.${NC}"
        echo "Usage: $0 ingest /pfad/zur/quelldatei.md"
        echo "       $0 ingest /pfad/zur/quelldatei.md --title \"Mein Titel\""
        exit 1
    fi

    if [ ! -f "$SOURCE_FILE" ]; then
        echo -e "${RED}❌ Fehler: Datei '$SOURCE_FILE' nicht gefunden.${NC}"
        exit 1
    fi

    # Optionalen Titel parsen
    local CUSTOM_TITLE=""
    if [ "${2:-}" = "--title" ] && [ -n "${3:-}" ]; then
        CUSTOM_TITLE="$3"
    fi

    echo -e "${YELLOW}📥 Ingest: $SOURCE_FILE${NC}"

    # ─── 6a. Quelldateinamen bestimmen ──────────────────────────────────────
    local SOURCE_BASENAME=$(basename "$SOURCE_FILE")
    local RAW_NAME="$(today)-${SOURCE_BASENAME}"
    local RAW_PATH="$RAW_DIR/$RAW_NAME"

    # ─── 6b. Quelle nach raw/ kopieren (immutable!) ─────────────────────────
    mkdir -p "$RAW_DIR"
    cp "$SOURCE_FILE" "$RAW_PATH"
    echo -e "${GREEN}✓ Quelle archiviert: $RAW_PATH${NC}"

    # ─── 6c. Wiki-Seite generieren ─────────────────────────────────────────
    local SOURCE_TEXT
    SOURCE_TEXT=$(cat "$SOURCE_FILE")

    # Titel bestimmen
    local PAGE_TITLE="$CUSTOM_TITLE"
    if [ -z "$PAGE_TITLE" ]; then
        # Erste Überschrift aus der Datei verwenden
        PAGE_TITLE=$(head -1 "$SOURCE_FILE" | sed 's/^#\+\s*//; s/^# //' || echo "$SOURCE_BASENAME")
    fi

    local PAGE_SLUG=$(slugify "$PAGE_TITLE")
    local PAGE_FILE="$WIKI_DIR/${PAGE_SLUG}.md"

    # Prüfen ob die Seite bereits existiert
    if [ -f "$PAGE_FILE" ]; then
        echo -e "${YELLOW}⚠ Seite '${PAGE_SLUG}.md' existiert bereits. Aktualisiere...${NC}"
        local MODE="update"
    else
        local MODE="create"
    fi

    # Zusammenfassung via LLM (optional)
    local SUMMARY=""
    if llm_available; then
        echo -e "${YELLOW}🧠 Generiere Zusammenfassung via $LLM_BACKEND...${NC}"
        SUMMARY=$(llm_summarize "$SOURCE_TEXT" "$PAGE_TITLE")
        echo -e "${GREEN}✓ Zusammenfassung erstellt${NC}"
    else
        echo -e "${YELLOW}⚠ Kein LLM-Backend verfügbar – verwende Rohtext als Basis${NC}"
    fi

    # Wiki-Seite schreiben
    cat > "$PAGE_FILE" <<-PAGEEOF
---
title: "$PAGE_TITLE"
source: "$RAW_NAME"
created: $(today)
tags: []
---

# $PAGE_TITLE

> **Quelle:** \`$RAW_NAME\` (archiviert in \`raw/\`)
> **Ingest-Datum:** $(today)

## Zusammenfassung

$(if [ -n "$SUMMARY" ]; then echo "$SUMMARY"; else echo "_Keine Zusammenfassung erstellt._"; fi)

---

## Original-Inhalt

$(cat "$SOURCE_FILE")

---

## Querverweise

- Siehe auch: [[index.md]]

PAGEEOF

    echo -e "${GREEN}✓ ${MODE} Seite: $PAGE_FILE${NC}"

    # ─── 6d. index.md aktualisieren ──────────────────────────────────────
    update_index

    # ─── 6e. log.md aktualisieren ────────────────────────────────────────
    append_log "ingest" "$PAGE_TITLE" "Quelle: $SOURCE_BASENAME → ${PAGE_SLUG}.md"

    # ─── 6f. qmd-Sync ────────────────────────────────────────────────────
    sync_wiki

    echo ""
    echo -e "${GREEN}✅ Ingest abgeschlossen: '$PAGE_TITLE'${NC}"
    echo "   • Rohquelle: $RAW_PATH"
    echo "   • Wiki-Seite: $PAGE_FILE"
    echo "   • Export möglich via: $0 export ${PAGE_SLUG}.md"
}

# ─── 7. LINT ──────────────────────────────────────────────────────────────────
lint_wiki() {
    echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   🔍 Wiki-Gesundheitscheck (Lint)    ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
    echo ""

    local issues=0

    # ─── 7a. Orphan-Seiten (keine eingehenden Links) ──────────────────────
    echo -e "${YELLOW}📄 Orphan-Seiten (keine eingehenden Links):${NC}"
    while IFS= read -r page; do
        local pagename=$(basename "$page")
        # Ignoriere index.md und log.md
        [[ "$pagename" == "index.md" || "$pagename" == "log.md" ]] && continue

        # Suche nach [[pagename]] in allen anderen Seiten
        local backlinks=$(rg -l "\[\[${pagename%%.*}\]\]" "$WIKI_DIR" 2>/dev/null \
            | grep -v "$pagename" || true)
        if [ -z "$backlinks" ]; then
            echo -e "   ${RED}⚠ $pagename${NC}"
            issues=$((issues + 1))
        fi
    done < <(find "$WIKI_DIR" -maxdepth 1 -name "*.md" | sort)

    if [ "$issues" -eq 0 ]; then
        echo -e "   ${GREEN}✓ Keine verwaisten Seiten gefunden${NC}"
    fi

    # ─── 7b. Erwähnte Seiten ohne eigene Datei ────────────────────────────
    echo ""
    echo -e "${YELLOW}🔗 Erwähnte aber fehlende Seiten:${NC}"
    local missing=0
    local refs=$(rg -o '\[\[([^\]]+)\]\]' "$WIKI_DIR" 2>/dev/null \
        | sed 's/.*\[\[\([^]]*\)\]\].*/\1/' \
        | sed 's/\.md$//' | sort -u || true)

    while IFS= read -r ref; do
        [ -z "$ref" ] && continue
        local ref_page="$WIKI_DIR/${ref}.md"
        if [ ! -f "$ref_page" ]; then
            echo -e "   ${YELLOW}🔗 [[${ref}]] – erwähnt, aber keine Seite vorhanden${NC}"
            missing=$((missing + 1))
        fi
    done <<< "$refs"

    if [ "$missing" -eq 0 ]; then
        echo -e "   ${GREEN}✓ Alle verlinkten Seiten existieren${NC}"
    fi

    # ─── 7c. Allgemeine Statistik ─────────────────────────────────────────
    echo ""
    echo -e "${YELLOW}📊 Statistik:${NC}"
    local total_files=$(find "$WIKI_DIR" -maxdepth 1 -name "*.md" \
        ! -name "index.md" ! -name "log.md" | wc -l)
    local raw_files=$(find "$RAW_DIR" -type f 2>/dev/null | wc -l)
    local total_words=$(find "$WIKI_DIR" -maxdepth 1 -name "*.md" \
        -exec wc -w {} + 2>/dev/null | tail -1 | awk '{print $1}')

    echo "   • Wiki-Seiten: $total_files"
    echo "   • Rohquellen:  $raw_files"
    echo "   • Gesamtwörter: ${total_words:-0}"
    echo "   • Gefundene Probleme: $issues"

    # ─── 7d. qmd-Suche prüfen ───────────────────────────────────────────
    echo ""
    echo -e "${YELLOW}🔎 qmd-Integration:${NC}"
    if command -v qmd &>/dev/null; then
        if qmd collection list 2>/dev/null | grep -q "$COLLECTION_NAME"; then
            echo -e "   ${GREEN}✓ Collection '$COLLECTION_NAME' verfügbar${NC}"
        else
            echo -e "   ${RED}⚠ Collection '$COLLECTION_NAME' nicht gefunden – 'qmd collection add ./wiki --name $COLLECTION_NAME'${NC}"
            issues=$((issues + 1))
        fi
    else
        echo -e "   ${YELLOW}⚠ qmd nicht installiert${NC}"
    fi

    echo ""
    if [ "$issues" -eq 0 ]; then
        echo -e "${GREEN}✅ Wiki ist gesund! Keine Probleme gefunden.${NC}"
    else
        echo -e "${YELLOW}⚠ $issues potenzielle(r) Verbesserungspunkt(e) gefunden.${NC}"
    fi

    # In Log eintragen
    append_log "lint" "Gesundheitscheck" "$issues Probleme gefunden"
}

# ─── 8. STATUS ────────────────────────────────────────────────────────────────
status_wiki() {
    echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   📊 Wiki-Status                     ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
    echo ""

    # Seiten zählen
    local wiki_pages=$(find "$WIKI_DIR" -maxdepth 1 -name "*.md" \
        ! -name "index.md" ! -name "log.md" | wc -l)
    local raw_sources=$(find "$RAW_DIR" -type f 2>/dev/null | wc -l)
    local exported=$(find "$EXPORT_DIR" -type f 2>/dev/null | wc -l)
    local wiki_words=$(find "$WIKI_DIR" -maxdepth 1 -name "*.md" \
        -exec cat {} + 2>/dev/null | wc -w)

    echo -e "${CYAN}📁 Wiki:${NC}"
    echo "   Pfad:    $(realpath "$WIKI_DIR")"
    echo "   Seiten:  $wiki_pages"
    echo "   Wörter:  $wiki_words"
    echo ""
    echo -e "${CYAN}📦 Rohquellen (raw/):${NC}"
    echo "   Dateien: $raw_sources"
    echo "   Pfad:    $(realpath "$RAW_DIR")"
    echo ""
    echo -e "${CYAN}📄 Exportiert (output_docs/):${NC}"
    echo "   Dateien: $exported"
    echo ""
    echo -e "${CYAN}⚙️  LLM-Backend:${NC}"
    echo "   Aktuell: $LLM_BACKEND"
    if [ "$LLM_BACKEND" = "ollama" ]; then
        echo "   Modell:  $OLLAMA_MODEL"
        if command -v ollama &>/dev/null; then
            echo "   Status:  $(ollama list 2>/dev/null | head -3 || echo 'nicht erreichbar')"
        fi
    fi
    echo ""
    echo -e "${CYAN}🔎 qmd-Suche:${NC}"
    if command -v qmd &>/dev/null; then
        echo "   Collection: $COLLECTION_NAME"
        qmd collection list 2>/dev/null | grep "$COLLECTION_NAME" || echo "   Status: nicht verbunden"
    else
        echo "   Status: nicht installiert"
    fi
    echo ""
    echo -e "${CYAN}🛠  Tools:${NC}"
    for tool in qmd jq ollama agy opencode; do
        if command -v "$tool" &>/dev/null; then
            echo "   ✅ $tool"
        else
            echo "   ❌ $tool (nicht installiert)"
        fi
    done

    append_log "status" "Wiki-Status abgefragt" "wiki=$wiki_pages, raw=$raw_sources, export=$exported"
}

# ─── 9. CONFIG ────────────────────────────────────────────────────────────────
show_config() {
    echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   ⚙️  Konfiguration                   ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Verzeichnisse:${NC}"
    echo "   WIKI_DIR:      $WIKI_DIR"
    echo "   RAW_DIR:       $RAW_DIR"
    echo "   EXPORT_DIR:    $EXPORT_DIR"
    echo ""
    echo -e "${CYAN}qmd:${NC}"
    echo "   COLLECTION:    $COLLECTION_NAME"
    echo ""
    echo -e "${CYAN}LLM-Backend:${NC}"
    echo "   LLM_BACKEND:   ${LLM_BACKEND:-ollama}"
    echo "   OLLAMA_MODEL:  ${OLLAMA_MODEL:-llama3.2:3b}"
    echo ""
    echo -e "${CYAN}Umgebungsvariablen überschreiben:${NC}"
    echo "   LLM_BACKEND=agy ./wiki.sh ..."
    echo "   OLLAMA_MODEL=mistral ./wiki.sh ..."
}

# ═══════════════════════════════════════════════════════════════════════════════
# HAUPTMENÜ
# ═══════════════════════════════════════════════════════════════════════════════
case "${1:-help}" in
    init)
        init_wiki
        ;;
    sync)
        sync_wiki
        ;;
    reindex)
        update_index
        append_log "reindex" "Index neu generiert"
        echo -e "${GREEN}✅ Index neu aufgebaut.${NC}"
        ;;
    search)
        search_wiki "${2:-}"
        ;;
    export)
        export_wiki "${2:-}"
        ;;
    list)
        list_wiki
        ;;
    ingest)
        ingest_wiki "${2:-}" "${3:-}" "${4:-}"
        ;;
    lint)
        lint_wiki
        ;;
    status)
        status_wiki
        ;;
    config)
        show_config
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        echo -e "${RED}❌ Unbekannter Befehl: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
