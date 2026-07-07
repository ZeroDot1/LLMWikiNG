import os
import re
import subprocess
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import markdown

PROJECT_ROOT = Path(__file__).resolve().parent
WIKI_DIR = PROJECT_ROOT / "wiki"
RAW_DIR = PROJECT_ROOT / "raw"
APP_VERSION = "1.6.0"

# Blueprint initialisieren
editor_bp = Blueprint("editor", __name__)

@editor_bp.route("/edit", methods=["GET"])
def edit_file():
    filename = request.args.get("filename", "")
    folder = request.args.get("folder", "wiki")  # "wiki" oder "raw"
    content = ""
    
    target_dir = WIKI_DIR if folder == "wiki" else RAW_DIR
    
    if filename:
        # Falls eine existierende Datei bearbeitet werden soll
        # Dateiname normalisieren/säubern
        clean_filename = filename
        if not clean_filename.endswith(".md"):
            clean_filename += ".md"
        
        filepath = target_dir / clean_filename
        if filepath.exists() and filepath.is_file():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                filename = clean_filename
            except Exception:
                pass

    # Python- und Flask-Versionen ermitteln für das Sidebar/About-Panel
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
        "editor.html",  # Verwende das existierende Template
        active_page="editor",
        filename=filename,
        content=content,
        folder=folder,
        app_version=APP_VERSION,
        python_version=sys.version.split()[0],
        flask_version=flask.__version__,
        uvicorn_version=uvicorn.__version__,
        markdown_version=markdown.__version__,
        qmd_version=qmd_version,
        jinja_version=jinja_version
    )

@editor_bp.route("/edit/preview", methods=["POST"])
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

@editor_bp.route("/edit/save", methods=["POST"])
def save_file():
    filename = request.form.get("filename", "").strip()
    content = request.form.get("content", "")
    folder = request.form.get("folder", "wiki")  # "wiki" oder "raw"
    
    if not filename:
        return redirect(url_for("editor.edit_file") + f"?folder={folder}&error_msg=Dateiname+erforderlich")
        
    # Dateiname säubern
    if not filename.endswith(".md"):
        filename += ".md"
        
    target_dir = WIKI_DIR if folder == "wiki" else RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / filename
    
    try:
        filepath.write_text(content, encoding="utf-8")
        
        # Logbuch und Index eintragen bzw. Sync anstoßen
        try:
            from llmWiki import append_okf_log, do_sync
            action_type = "Update" if filepath.exists() else "Creation"
            append_okf_log(action_type, filename, f"Datei im Browser-Editor bearbeitet ({folder})")
            do_sync()
        except Exception:
            pass
            
        success_msg = f"Datei '{filename}' erfolgreich in {folder}/ gespeichert."
        
        if folder == "wiki":
            # Redirect zur neu erstellten/bearbeiteten Wiki-Seite
            page_slug = filename[:-3]
            return redirect(url_for("wiki_page", page_name=page_slug) + f"?success_msg={success_msg}")
        else:
            # Redirect zur Pending-Seite für Rohquellen
            return redirect(url_for("pending_ingests") + f"?success_msg={success_msg}")
            
    except Exception as e:
        return redirect(url_for("editor.edit_file") + f"?filename={filename}&folder={folder}&error_msg=Fehler beim Speichern: {e}")
