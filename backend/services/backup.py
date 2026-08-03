# LLMWikiNG – Copyright (C) 2026 ZeroDot1
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0-or-later).
# SPDX-License-Identifier: AGPL-3.0-or-later
import os
import tarfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.config import PROJECT_ROOT

BACKUP_DIR = PROJECT_ROOT / "backups"

def get_backup_dir() -> Path:
    """Gibt das dedizierte Server-Backup-Verzeichnis zurück und erstellt es bei Bedarf."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR

def create_backup_xz(output_path: Path | None = None) -> Path:
    """Packt alle Wiki-Daten in ein tar.xz-Archiv.
    
    Falls output_path None ist, wird automatisch eine Zeitstempel-Datei im
    Server-Backup-Verzeichnis (`backups/`) erstellt.
    """
    dirs_to_backup = ["wikis", "raw", "data"]
    files_to_backup = ["config.json"]

    if output_path is None:
        b_dir = get_backup_dir()
        filename = f"llmwiki_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.xz"
        output_path = b_dir / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output_path, "w:xz") as tar:
        for d in dirs_to_backup:
            dir_path = PROJECT_ROOT / d
            if dir_path.exists():
                tar.add(dir_path, arcname=d)

        for f in files_to_backup:
            file_path = PROJECT_ROOT / f
            if file_path.exists():
                tar.add(file_path, arcname=f)

    return output_path

def restore_backup_xz(archive_path: Path) -> None:
    """Entpackt ein tar.xz-Archiv und überschreibt die bestehenden Daten."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="llmwiki_restore_") as tmp:
        temp_dir = Path(tmp)
        with tarfile.open(archive_path, "r:xz") as tar:
            tar.extractall(path=temp_dir)

        archive_path_abs = archive_path.resolve()

        for item in temp_dir.iterdir():
            dest_path = PROJECT_ROOT / item.name
            if item.is_dir():
                if dest_path.exists():
                    # Falls archive_path im Zielordner liegt, verschieben wir das Archiv temporär
                    if archive_path_abs.is_relative_to(dest_path.resolve()):
                        temp_safe_archive = PROJECT_ROOT / f"_safe_{archive_path.name}"
                        shutil.move(archive_path_abs, temp_safe_archive)
                        shutil.rmtree(dest_path)
                        shutil.copytree(item, dest_path)
                        dest_path_new_archive = dest_path / archive_path.name
                        dest_path_new_archive.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(temp_safe_archive, dest_path_new_archive)
                        continue
                    shutil.rmtree(dest_path)
                shutil.copytree(item, dest_path)
            else:
                if dest_path.exists():
                    os.remove(dest_path)
                shutil.copy(item, dest_path)

def list_server_backups() -> list[dict]:
    """Listet alle auf dem Server gespeicherten Backup-Dateien aus `backups/` und `data/` sortiert nach Datum auf."""
    backups = []
    seen_names = set()

    for folder in [get_backup_dir(), PROJECT_ROOT / "data"]:
        if not folder.exists():
            continue
        for p in folder.glob("*.tar.xz"):
            if p.name in seen_names or p.name.startswith("temp_"):
                continue
            seen_names.add(p.name)
            stat = p.stat()
            backups.append({
                "filename": p.name,
                "filepath": str(p),
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "created_at_fmt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%d.%m.%Y %H:%M:%S"),
                "location": "backups" if folder == BACKUP_DIR else "data",
            })

    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups

def delete_server_backup(filename: str) -> bool:
    """Löscht eine bestimmte Backup-Datei sicher von Disk."""
    safe_filename = os.path.basename(filename)
    if not safe_filename.endswith(".tar.xz"):
        return False

    for folder in [get_backup_dir(), PROJECT_ROOT / "data"]:
        target = folder / safe_filename
        if target.exists() and target.is_file():
            target.unlink()
            return True
    return False

def get_backup_filepath(filename: str) -> Path | None:
    """Gibt den Pfad einer Backup-Datei zurück, falls existiert."""
    safe_filename = os.path.basename(filename)
    if not safe_filename.endswith(".tar.xz"):
        return None

    for folder in [get_backup_dir(), PROJECT_ROOT / "data"]:
        target = folder / safe_filename
        if target.exists() and target.is_file():
            return target
    return None

