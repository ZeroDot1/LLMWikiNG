import os
import re
import subprocess
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import markdown

PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "raw"
APP_VERSION = "1.5.0"

# Blueprint initialisieren
raw_editor_bp = Blueprint("raw_editor", __name__)

@raw_editor_bp.route("/raw/edit", methods=["GET"])
def edit_raw():
    filename = request.args.get("filename", "")
    content = ""
    if filename:
        # Falls eine existierende Datei bearbeitet werden soll
        # Dateiname säubern
        filename = os.path.basename(filename)
        filepath = RAW_DIR / filename
        if filepath.exists() and filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    
    # Python- und Flask-Versionen ermitteln für das about-Panel/Sidebar
    import sys
    import flask
    import uvicorn
    from jinja2 import __version__ as jinja_version
    
    # qmd-Version ermitteln
    qmd_version = "nicht installiert"
    try:
        res = subprocess.run(["qmd", "--version"], capture_output=True, text=True)
        if res.returncode == 0:
            qmd_version = res.stdout.strip()
    except Exception:
        pass

    return render_template(
        "raw_editor.html",
        active_page="raw_editor",
        filename=filename,
        content=content,
        app_version=APP_VERSION,
        python_version=sys.version.split()[0],
        flask_version=flask.__version__,
        uvicorn_version=uvicorn.__version__,
        markdown_version=markdown.__version__,
        qmd_version=qmd_version,
        jinja_version=jinja_version
    )

@raw_editor_bp.route("/raw/edit/preview", methods=["POST"])
def preview_markdown():
    text = request.form.get("content", "")
    # Frontmatter entfernen für Vorschau
    text = re.sub(r'^---.*?---\s*', '', text, flags=re.DOTALL)
    html = markdown.markdown(
        text,
        extensions=["toc", "tables", "fenced_code", "codehilite"],
        extension_configs={
            "toc": {
                "marker": "[TOC]",
                "permalink": True,
            },
        }
    )
    return html

@raw_editor_bp.route("/raw/edit/save", methods=["POST"])
def save_raw():
    filename = request.form.get("filename", "").strip()
    content = request.form.get("content", "")
    
    if not filename:
        return redirect(url_for("raw_editor.edit_raw") + "?error_msg=Dateiname+erforderlich")
        
    # Dateiname säubern
    filename = os.path.basename(filename)
    if not filename.endswith(".md"):
        filename += ".md"
        
    # Sicherstellen, dass RAW_DIR existiert
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RAW_DIR / filename
    
    try:
        filepath.write_text(content, encoding="utf-8")
        
        # Logbuch eintragen über llmWiki
        try:
            from llmWiki import append_okf_log, do_sync
            append_okf_log("Creation", filename, "Rohquelle im Browser erstellt/bearbeitet")
            do_sync()
        except Exception:
            pass
            
        success_msg = f"Datei '{filename}' erfolgreich in raw/ gespeichert."
        # Redirect zur Pending-Seite
        return redirect(url_for("pending_ingests") + f"?success_msg={success_msg}")
    except Exception as e:
        return redirect(url_for("raw_editor.edit_raw") + f"?filename={filename}&error_msg=Fehler beim Speichern: {e}")
