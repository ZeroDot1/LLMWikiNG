#!/usr/bin/env bash
#
# docker-compose-tui.sh  (ohne fzf - reine Bash-TUI mit Nummernmenues)
# ----------------------------------------------------------------------
# Funktionen:
#   * Compose-Datei erkennen (docker-compose.*, compose.*, per Inhalt, oder manuell)
#   * Compose-Aktionen: up, down, build, restart, pull, logs, ps, config
#   * Image exportieren: einzeln, mehrere (Komma/Leerzeichen) oder alle Images
#     eines Compose-Projekts -> komprimierte Tar-Datei (gzip/zstd/xz/bzip2/keine)
#   * Image importieren: docker load aus Tar-Datei
#
# Auf einem Zielserver einfach die Tar-Datei (und ggf. die compose-Datei)
# hinkopieren und "Image importieren" waehlen.
#
# Zusaetzlich:
#   * System-Pflege: prune (container/image/volume/network/system) direkt uebers Menue
#   * Container auflisten und Container samt zugehoeriger Volumes loeschen
#
# Umgebungsvariablen (optional):
#   COMPOSE_DIR   Verzeichnis fuer die Compose-Suche (Default: $PWD)
#   EXPORT_DIR    Verzeichnis fuer exportierte Images (Default: $COMPOSE_DIR/docker-exports)
#
set -uo pipefail   # kein 'set -e': eine fehlerhafte Aktion soll nicht das Skript toeten

# ----------------------------------------------------------------------------
# Konfiguration / Farben
# ----------------------------------------------------------------------------
COMPOSE_DIR="${COMPOSE_DIR:-$PWD}"
EXPORT_DIR="${EXPORT_DIR:-$COMPOSE_DIR/docker-exports}"

RED='\033[31m'; GREEN='\033[32m'; YEL='\033[33m'; BOLD='\033[1m'; CYAN='\033[36m'; NC='\033[0m'
hr() { printf '%s\n' "============================================================"; }
pause() { read -r -p "Enter druecken..." _; }

die() { echo -e "${RED}Fehler:${NC} $1" >&2; pause; exit 1; }

check_deps() {
    command -v docker >/dev/null 2>&1 || die "docker ist nicht installiert."
    docker info >/dev/null 2>&1 || die "Docker-Daemon laeuft nicht (sudo? dockerd?)."
}

# ----------------------------------------------------------------------------
# Generisches Nummernmenue
#   menu "Titel" "Option1" "Option2" ...
#   gibt die gewaehlte Optionszeile zurueck, bei Abbruch (0/ungueltig) LEER.
# ----------------------------------------------------------------------------
# WICHTIG: Das Menue wird nach STDERR ausgegeben (Anzeige), nur die gewaehlte
# Option geht nach STDOUT (Rueckgabewert). Sonst faengt $(menu ...) Titel+Optionen
# mit ein und der case-Vergleich im Aufrufer schlaegt fehl -> Endlosschleife.
menu() {
    local title="$1"; shift
    local opts=("$@")
    local i
    echo >&2
    echo -e "${BOLD}$title${NC}" >&2
    for i in "${!opts[@]}"; do
        printf "  %d) %s\n" $((i+1)) "${opts[$i]}" >&2
    done
    echo -e "  ${YEL}0) Zurueck / Abbrechen${NC}" >&2
    local ans
    read -r -p "Auswahl (Zahl): " ans
    if [[ "$ans" =~ ^[0-9]+$ ]] && [ "$ans" -ge 1 ] && [ "$ans" -le "${#opts[@]}" ]; then
        echo "${opts[$((ans-1))]}"
    else
        echo ""
    fi
}

# Befehl ausfuehren und Ergebnis zeigen
run_cmd() {
    local desc="$1"; shift
    clear
    hr; echo -e "  ${BOLD}$desc${NC}"; echo "  Befehl: $*"; hr; echo
    if "$@"; then echo; echo -e "${GREEN}>>> Erfolgreich beendet.${NC}"
    else echo; echo -e "${RED}>>> Befehl lieferte Fehlercode $?.${NC}"; fi
    echo; pause
}

# ----------------------------------------------------------------------------
# compose-Datei erkennen / auswaehlen
# ----------------------------------------------------------------------------
COMPOSE_FILE=""

select_compose_file() {
    local files=()
    while IFS= read -r f; do
        [ -n "$f" ] && files+=("$(cd "$(dirname "$f")" && pwd)/$(basename "$f")")
    done < <(find "$COMPOSE_DIR" -maxdepth 4 \( \
        -name 'docker-compose.yml' -o -name 'docker-compose.yaml' -o \
        -name 'compose.yml' -o -name 'compose.yaml' \) \
        -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | sort)
    while IFS= read -r f; do
        [ -n "$f" ] && files+=("$(cd "$(dirname "$f")" && pwd)/$(basename "$f")")
    done < <(find "$COMPOSE_DIR" -maxdepth 4 -type f \( -name '*.yml' -o -name '*.yaml' \) \
        -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null \
        | while IFS= read -r g; do grep -qE '^[[:space:]]*services:' "$g" 2>/dev/null && echo "$g"; done | sort -u)
    mapfile -t files < <(printf '%s\n' "${files[@]}" | sort -u)

    if [ "${#files[@]}" -eq 0 ]; then
        echo; echo "Keine Compose-Datei gefunden."
        read -r -p "Manuellen Pfad angeben (leer=Abbrechen): " manual
        [ -z "$manual" ] && return 1
        [ -f "$manual" ] || { echo "Datei existiert nicht."; sleep 1; return 1; }
        COMPOSE_FILE="$(cd "$(dirname "$manual")" && pwd)/$(basename "$manual")"
        return 0
    fi
    if [ "${#files[@]}" -eq 1 ]; then
        COMPOSE_FILE="${files[0]}"; echo "Compose-Datei gewaehlt: $COMPOSE_FILE"; sleep 1; return 0
    fi
    echo; echo -e "${BOLD}Compose-Datei waehlen:${NC}"
    local i
    for i in "${!files[@]}"; do printf "  %d) %s\n" $((i+1)) "${files[$i]}"; done
    echo -e "  ${YEL}0) Abbrechen${NC}"
    local ans
    read -r -p "Auswahl: " ans
    if [[ "$ans" =~ ^[0-9]+$ ]] && [ "$ans" -ge 1 ] && [ "$ans" -le "${#files[@]}" ]; then
        COMPOSE_FILE="${files[$((ans-1))]}"; return 0
    fi
    return 1
}

# Compose-Befehl im Projektverzeichnis ausfuehren (Subshell -> CWD unveraendert)
compose_run() {
    local file="$1"; shift
    local dir; dir="$(dirname "$file")"
    local base; base="$(basename "$file")"
    ( cd "$dir" && docker compose -f "$base" "$@" )
}

# Images eines Compose-Projekts ermitteln (repo:tag)
compose_images() {
    compose_run "$1" config --format yaml 2>/dev/null \
        | grep -E '^[[:space:]]*image:' \
        | awk '{print $2}' \
        | sed -E 's/^"|"$//g' \
        | sort -u
}

# ----------------------------------------------------------------------------
# compose-Aktionen
# ----------------------------------------------------------------------------
compose_actions() {
    [ -z "$COMPOSE_FILE" ] && { select_compose_file || return; }
    [ -z "$COMPOSE_FILE" ] && return

    while true; do
        local a
        a="$(menu "Compose-Aktionen | Datei: $COMPOSE_FILE" \
            "up        Container starten (up -d)" \
            "down      Container stoppen (down)" \
            "build     Images bauen (build)" \
            "restart   Container neu starten (restart)" \
            "pull      Images ziehen (pull)" \
            "logs      Live-Logs anzeigen (logs -f)" \
            "ps        Status der Container (ps)" \
            "config    Konfiguration pruefen (config)")"
        [ -z "$a" ] && return
        a="${a%% *}"
        case "$a" in
            up)      run_cmd "Container starten" compose_run "$COMPOSE_FILE" up -d ;;
            down)    run_cmd "Container stoppen" compose_run "$COMPOSE_FILE" down ;;
            build)   run_cmd "Images bauen" compose_run "$COMPOSE_FILE" build ;;
            restart) run_cmd "Container neu starten" compose_run "$COMPOSE_FILE" restart ;;
            pull)    run_cmd "Images ziehen" compose_run "$COMPOSE_FILE" pull ;;
            logs)    clear; echo "Live-Logs (STRG-C zum Abbrechen)..."; echo
                     compose_run "$COMPOSE_FILE" logs -f || true; pause ;;
            ps)      run_cmd "Container-Status" compose_run "$COMPOSE_FILE" ps ;;
            config)  run_cmd "Konfiguration pruefen" compose_run "$COMPOSE_FILE" config ;;
            *)       return ;;
        esac
    done
}

# ----------------------------------------------------------------------------
# Image exportieren
# ----------------------------------------------------------------------------
do_export() {
    local img_list=("$@")
    [ "${#img_list[@]}" -eq 0 ] && { echo "Keine Images zum Export."; sleep 1; return; }

    # Vorab pruefen, welche Images lokal existieren
    local valid=() missing=() img
    for img in "${img_list[@]}"; do
        if docker image inspect "$img" >/dev/null 2>&1; then valid+=("$img"); else missing+=("$img"); fi
    done
    if [ "${#missing[@]}" -gt 0 ]; then
        echo "Folgende Images existieren lokal NICHT (uebersprungen):"
        printf '  - %s\n' "${missing[@]}"; sleep 2
    fi
    if [ "${#valid[@]}" -eq 0 ]; then
        echo "Keine gueltigen Images zum Export (evtl. zuerst 'build'/'pull' ausfuehren)."
        sleep 2; return
    fi
    img_list=("${valid[@]}")

    # Kompression waehlen
    local comp
    comp="$(menu "Kompressionsverfahren waehlen" \
        "gzip  (.tar.gz)  - schnell, gute Kompatibilitaet" \
        "zstd  (.tar.zst) - sehr schnell, gute Komprimierung" \
        "xz    (.tar.xz)  - langsam, beste Komprimierung" \
        "bzip2 (.tar.bz2) - langsam, gute Komprimierung" \
        "keine (.tar)     - unkomprimiert, maximal schnell")"
    [ -z "$comp" ] && return
    comp="${comp%% *}"
    local ext cmd
    case "$comp" in
        gzip)  ext=tar.gz;  cmd="gzip" ;;
        zstd)  ext=tar.zst; cmd="zstd -" ;;
        xz)    ext=tar.xz;  cmd="xz -" ;;
        bzip2) ext=tar.bz2; cmd="bzip2 -" ;;
        keine) ext=tar;     cmd="cat" ;;
        *)     return ;;
    esac

    # Dateiname
    local default_name
    if [ "${#img_list[@]}" -eq 1 ]; then
        default_name="$(echo "${img_list[0]}" | tr '/:' '__')"
    else
        default_name="docker-images-$(date +%Y%m%d)"
    fi
    default_name="${default_name}.${ext}"
    mkdir -p "$EXPORT_DIR"
    local outfile
    read -r -p "Dateiname [$default_name]: " outfile
    [ -z "$outfile" ] && outfile="$default_name"
    case "$outfile" in
        /*) : ;;
        *.${ext}) : ;;
        *) outfile="${outfile}.${ext}" ;;
    esac
    case "$outfile" in
        /*) : ;;
        *) outfile="$EXPORT_DIR/$outfile" ;;
    esac
    mkdir -p "$(dirname "$outfile")"

    clear
    hr; echo -e "  ${BOLD}Image(s) exportieren${NC}"
    echo "  Quelle : ${img_list[*]}"
    echo "  Ziel   : $outfile"
    echo "  Methode: $cmd"; hr; echo

    if docker save "${img_list[@]}" | eval "$cmd" > "$outfile"; then
        local size; size="$(du -h "$outfile" | cut -f1)"
        echo; echo -e "${GREEN}>>> Export erfolgreich: $outfile ($size)${NC}"
        echo; echo "Auf dem Zielserver:"
        echo "    docker load -i $outfile"
    else
        echo; echo -e "${RED}>>> Export fehlgeschlagen.${NC}"
    fi
    echo; pause
}

export_menu() {
    while true; do
        local m
        m="$(menu "Image exportieren" \
            "compose   Alle Images des aktiven Compose-Projekts" \
            "select    Einzelne / mehrere Images waehlen" \
            "<< Zurueck zum Hauptmenue")"
        [ -z "$m" ] && return
        m="${m%% *}"

        case "$m" in
            compose)
                [ -z "$COMPOSE_FILE" ] && { select_compose_file || return; }
                [ -z "$COMPOSE_FILE" ] && return
                local imgs=()
                while IFS= read -r i; do [ -n "$i" ] && imgs+=("$i"); done < <(compose_images "$COMPOSE_FILE")
                if [ "${#imgs[@]}" -eq 0 ]; then
                    echo "Keine Images im Compose-Projekt gefunden."; sleep 1; continue
                fi
                do_export "${imgs[@]}"
                ;;
            select)
                local images=()
                while IFS= read -r i; do [ -n "$i" ] && images+=("$i"); done < <(
                    docker images --format '{{.Repository}}:{{.Tag}}' | grep -v '<none>' | sort)
                if [ "${#images[@]}" -eq 0 ]; then
                    echo "Keine Images lokal vorhanden."; sleep 1; return
                fi
                echo; echo -e "${BOLD}Images waehlen (eine Zahl, oder mehrere durch Komma/Leerzeichen):${NC}"
                local i
                for i in "${!images[@]}"; do printf "  %d) %s\n" $((i+1)) "${images[$i]}"; done
                echo -e "  ${YEL}0) Abbrechen${NC}"
                local ans
                read -r -p "Auswahl: " ans
                [ "$ans" = "0" ] && continue
                local sel=() nums n
                IFS=', ' read -r -a nums <<< "$ans"
                for n in "${nums[@]}"; do
                    if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "${#images[@]}" ]; then
                        sel+=("${images[$((n-1))]}")
                    fi
                done
                if [ "${#sel[@]}" -eq 0 ]; then echo "Ungueltige Auswahl."; sleep 1; continue; fi
                do_export "${sel[@]}"
                ;;
            "<<") return ;;
            *) return ;;
        esac
    done
}

# ----------------------------------------------------------------------------
# Image importieren
# ----------------------------------------------------------------------------
import_image() {
    mkdir -p "$EXPORT_DIR"
    local files=()
    while IFS= read -r f; do [ -n "$f" ] && files+=("$f"); done < <(
        find "$EXPORT_DIR" "$PWD" -maxdepth 2 -type f \( \
            -name '*.tar' -o -name '*.tar.gz' -o -name '*.tar.zst' -o \
            -name '*.tar.xz' -o -name '*.tar.bz2' \) 2>/dev/null | sort -u)

    if [ "${#files[@]}" -eq 0 ]; then
        die "Keine Image-Tar-Dateien in '$EXPORT_DIR' oder '$PWD' gefunden."
    fi
    echo; echo -e "${BOLD}Image-Datei zum Importieren waehlen:${NC}"
    local i
    for i in "${!files[@]}"; do printf "  %d) %s\n" $((i+1)) "${files[$i]}"; done
    echo -e "  ${YEL}0) Abbrechen${NC}"
    local ans
    read -r -p "Auswahl: " ans
    [ "$ans" = "0" ] && return
    if [[ "$ans" =~ ^[0-9]+$ ]] && [ "$ans" -ge 1 ] && [ "$ans" -le "${#files[@]}" ]; then
        local file="${files[$((ans-1))]}"
        clear; hr; echo -e "  ${BOLD}Image importieren (docker load)${NC}"; echo "  Datei: $file"; hr; echo
        if docker load -i "$file"; then
            echo; echo -e "${GREEN}>>> Import erfolgreich.${NC}"
        else
            echo; echo -e "${RED}>>> Import fehlgeschlagen.${NC}"
        fi
        echo; pause
    fi
}

# ----------------------------------------------------------------------------
# System-Pflege: prune
# ----------------------------------------------------------------------------
prune_menu() {
    while true; do
        local p
        p="$(menu "System-Pflege (prune) - ACHTUNG: loescht ungenutzte Objekte" \
            "container  Gestoppte Container entfernen (docker container prune)" \
            "image      Unbenutzte Images entfernen (docker image prune -a)" \
            "volume     Unbenutzte Volumes entfernen (docker volume prune)" \
            "network    Unbenutzte Netzwerke entfernen (docker network prune)" \
            "system     Alles (container+image+network, ohne volumes) (docker system prune)" \
            "system-all Vollstaendig inkl. Volumes (docker system prune -a --volumes)" \
            "<< Zurueck zum Hauptmenue")"
        [ -z "$p" ] && return
        p="${p%% *}"

        case "$p" in
            container)
                echo -e "${YEL}Entfernt ALLE gestoppten Container.${NC}"; sleep 1
                run_cmd "Container prune" docker container prune -f
                ;;
            image)
                echo -e "${YEL}Entfernt ALLE unbenutzten Images (nicht von laufenden Containern).${NC}"; sleep 1
                run_cmd "Image prune (alle)" docker image prune -a -f
                ;;
            volume)
                echo -e "${RED}ACHTUNG: Loescht ALLE unbenutzten Volumes (Datenverlust moeglich!).${NC}"; sleep 1
                run_cmd "Volume prune" docker volume prune -f
                ;;
            network)
                echo -e "${YEL}Entfernt ALLE unbenutzten Netzwerke.${NC}"; sleep 1
                run_cmd "Network prune" docker network prune -f
                ;;
            system)
                echo -e "${YEL}Entfernt container+image+network (KEINE volumes).${NC}"; sleep 1
                run_cmd "System prune" docker system prune -f
                ;;
            system-all)
                echo -e "${RED}ACHTUNG: Loescht ALLES inkl. Volumes (Datenverlust moeglich!).${NC}"; sleep 1
                run_cmd "System prune (vollstaendig)" docker system prune -a -f --volumes
                ;;
            "<<") return ;;
            *) return ;;
        esac
    done
}

# ----------------------------------------------------------------------------
# Container auflisten + Container samt Volumes loeschen
# ----------------------------------------------------------------------------
container_menu() {
    while true; do
        local m
        m="$(menu "Container verwalten" \
            "list      Alle Container auflisten (laufend + gestoppt)" \
            "stop-all  ALLE laufenden Container auf dem Host stoppen" \
            "remove    Container auswaehlen und samt Volumes loeschen" \
            "<< Zurueck zum Hauptmenue")"
        [ -z "$m" ] && return
        m="${m%% *}"

        case "$m" in
            list)
                clear
                hr; echo -e "  ${BOLD}Alle Container${NC}"; hr; echo
                docker ps -a --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Size}}'
                echo; pause
                ;;
            stop-all)
                local running_ids
                running_ids=$(docker ps -q)
                if [ -z "$running_ids" ]; then
                    echo "Keine laufenden Container auf dem Host."; sleep 1; continue
                fi
                echo -e "${YEL}Stoppe ALLE laufenden Container...${NC}"
                run_cmd "Stoppe alle laufenden Container" docker stop $running_ids
                ;;

            remove)
                # Container auflisten (ID, Name, Status)
                local ids=() names=() statuses=()
                while IFS=$'\t' read -r cid cname cstatus; do
                    [ -z "$cid" ] && continue
                    ids+=("$cid"); names+=("$cname"); statuses+=("$cstatus")
                done < <(docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.Status}}')

                if [ "${#ids[@]}" -eq 0 ]; then
                    echo "Keine Container vorhanden."; sleep 1; continue
                fi

                clear
                hr; echo -e "  ${BOLD}Container zum Loeschen auswaehlen${NC}"; hr; echo
                local i
                for i in "${!ids[@]}"; do
                    printf "  %d) %s  |  %s  |  %s\n" $((i+1)) "${names[$i]}" "${statuses[$i]}" "${ids[$i]}"
                done
                echo -e "  ${YEL}0) Abbrechen${NC}"
                echo -e "  ${CYAN}Mehrere durch Komma/Leerzeichen trennen (z.B. 1,3 5)${NC}"
                local ans
                read -r -p "Auswahl: " ans
                [ "$ans" = "0" ] && continue
                [ -z "$ans" ] && { echo "Keine Auswahl."; sleep 1; continue; }

                local sel_idx=() nums n
                IFS=', ' read -r -a nums <<< "$ans"
                for n in "${nums[@]}"; do
                    if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -ge 1 ] && [ "$n" -le "${#ids[@]}" ]; then
                        sel_idx+=("$((n-1))")
                    fi
                done
                if [ "${#sel_idx[@]}" -eq 0 ]; then
                    echo "Ungueltige Auswahl."; sleep 1; continue
                fi

                # Zusammenfassung + Volumes der gewaehlten Container sammeln
                local sel_ids=() sel_names=() vol_names=()
                echo; echo -e "${BOLD}Folgende Container werden GELoescht:${NC}"
                for i in "${sel_idx[@]}"; do
                    echo -e "  - ${names[$i]} (${ids[$i]})"
                    sel_ids+=("${ids[$i]}"); sel_names+=("${names[$i]}")
                    # Volumes dieses Containers (Mounts vom Typ volume)
                    while IFS= read -r v; do
                        [ -n "$v" ] && vol_names+=("$v")
                    done < <(docker inspect -f '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}{{println}}{{end}}{{end}}' "${ids[$i]}" 2>/dev/null)
                done

                # Duplikate aus Volumes entfernen
                if [ "${#vol_names[@]}" -gt 0 ]; then
                    mapfile -t vol_names < <(printf '%s\n' "${vol_names[@]}" | sort -u)
                    echo; echo -e "${YEL}Zugehoerige Volumes (werden ebenfalls geloescht):${NC}"
                    printf '  - %s\n' "${vol_names[@]}"
                fi

                echo; echo -e "${RED}ACHTUNG: Container + Volumes unwiderruflich loeschen?${NC}"
                read -r -p "Bestaetigen (ja/NEIN): " confirm
                if [ "${confirm,,}" != "ja" ]; then
                    echo "Abgebrochen."; sleep 1; continue
                fi

                # Container stoppen (falls laufend) + entfernen inkl. anonymen Volumes
                clear
                hr; echo -e "  ${BOLD}Container + Volumes loeschen${NC}"; hr; echo
                if docker rm -f -v "${sel_ids[@]}"; then
                    echo -e "${GREEN}>>> Container entfernt.${NC}"
                else
                    echo -e "${RED}>>> Fehler beim Entfernen der Container.${NC}"
                fi
                # Benannte Volumes explizit loeschen (docker rm -v loescht nur anonyme)
                if [ "${#vol_names[@]}" -gt 0 ]; then
                    echo; echo "Loesche benannte Volumes:"
                    for v in "${vol_names[@]}"; do
                        if docker volume rm "$v" 2>/dev/null; then
                            echo -e "  ${GREEN}✓ $v${NC}"
                        else
                            echo -e "  ${RED}✗ $v (belegt oder nicht gefunden)${NC}"
                        fi
                    done
                fi
                echo; pause
                ;;
            "<<") return ;;
            *) return ;;
        esac
    done
}

# ----------------------------------------------------------------------------
# Hauptmenue
# ----------------------------------------------------------------------------
main() {
    check_deps
    mkdir -p "$EXPORT_DIR"
    while true; do
        local c
        c="$(menu "Docker Compose TUI | Verz: $COMPOSE_DIR | Export: $EXPORT_DIR | Compose: ${COMPOSE_FILE:-<keine>}" \
            "Compose-Datei waehlen / erkennen" \
            "Compose-Aktionen ausfuehren" \
            "Image exportieren (save -> tar)" \
            "Image importieren (load <- tar)" \
            "Container verwalten (auflisten + loeschen inkl. Volumes)" \
            "System-Pflege (prune: container/image/volume/network/system)" \
            "Beenden")"
        [ -z "$c" ] && break
        case "$c" in
            "Compose-Datei"*)     select_compose_file || true ;;
            "Compose-Aktionen"*)  compose_actions || true ;;
            "Image exportieren"*) export_menu || true ;;
            "Image importieren"*) import_image || true ;;
            "Container verwalten"*) container_menu || true ;;
            "System-Pflege"*)     prune_menu || true ;;
            "Beenden"*)           break ;;
            *) : ;;
        esac
    done
    clear
    echo "Tschuess!"
}

main "$@"
