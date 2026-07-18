import json
import os
import shutil
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("data")
WIKIS_ROOT = Path("wikis")
DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_directory_size(path):
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total

def list_wikis():
    wikis_file = DATA_DIR / "wikis.json"
    
    # Initialize from WIKIS_ROOT if wikis.json doesn't exist
    if not wikis_file.exists():
        initial_wikis = []
        if WIKIS_ROOT.exists():
            for d in sorted(WIKIS_ROOT.iterdir()):
                if d.is_dir():
                    meta = d / "wiki.json"
                    name = d.name
                    display = name
                    desc = ""
                    if meta.exists():
                        try:
                            data = json.loads(meta.read_text(encoding="utf-8"))
                            display = data.get("name", name)
                            desc = data.get("description", "")
                        except Exception:
                            pass
                    initial_wikis.append({
                        "slug": name,
                        "name": display,
                        "description": desc,
                        "created_at": datetime.now().isoformat()
                    })
        wikis_file.write_text(json.dumps(initial_wikis, indent=2), encoding="utf-8")

    try:
        stored_wikis = json.loads(wikis_file.read_text(encoding="utf-8"))
    except Exception:
        stored_wikis = []

    # Filter out missing directories and update dynamic stats
    result = []
    for w in stored_wikis:
        d = WIKIS_ROOT / w["slug"]
        if d.exists() and d.is_dir():
            page_count = sum(1 for _ in d.rglob("*.md") if _.stem not in ("index", "log", "ingestlater"))
            w["page_count"] = page_count
            w["size"] = get_directory_size(d)
            w["status"] = "online"
            result.append(w)

    return result

print(list_wikis())
