import os
import re
import yaml
from datetime import datetime

WIKI_DIR = "/home/user/Dokumente/GitHub/LLMWikiNG/wiki"

def convert_links(content):
    # Konvertiert [[seite.md]] -> [seite](seite.md)
    def repl(match):
        link = match.group(1).strip()
        display_name = link.replace(".md", "").replace("-", " ").title()
        return f"[{display_name}]({link})"
    
    return re.sub(r"\[\[(.*?)\]\]", repl, content)

def migrate_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # Trennung Frontmatter und Body
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        # Check if it has no frontmatter (e.g. index/log)
        new_body = convert_links(text)
        if new_body != text:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_body)
        return
    
    try:
        end_idx = lines.index("---", 1)
    except ValueError:
        return
        
    fm_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx+1:])
    
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return

    # OKF-Spezifische Anpassungen
    changed = False
    if 'type' not in fm:
        fm['type'] = 'Concept'
        changed = True
    
    if 'created' in fm and 'timestamp' not in fm:
        fm['timestamp'] = f"{fm['created']}T00:00:00Z"
        del fm['created']
        changed = True
        
    if 'source' in fm and 'resource' not in fm:
        fm['resource'] = f"file://raw/{fm['source']}"
        del fm['source']
        changed = True

    # Links im Body konvertieren
    new_body = convert_links(body)
    if new_body != body:
        changed = True
    
    if changed:
        new_fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
        new_content = f"---\n{new_fm_text}\n---\n\n{new_body}"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Migrated: {filepath}")

# Start der Migration über alle *.md-Dateien
for root, _, files in os.walk(WIKI_DIR):
    for file in files:
        if file.endswith(".md"):
            migrate_file(os.path.join(root, file))
