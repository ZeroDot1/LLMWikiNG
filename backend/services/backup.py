import os
import tarfile
import shutil
from pathlib import Path
from core.config import PROJECT_ROOT

def create_backup_xz(output_path: Path) -> Path:
    """Packt alle Wiki-Daten in ein tar.xz-Archiv."""
    dirs_to_backup = ["wikis", "raw", "data"]
    files_to_backup = ["config.json"]

    with tarfile.open(output_path, "w:xz") as tar:
        # Ordner sichern
        for d in dirs_to_backup:
            dir_path = PROJECT_ROOT / d
            if dir_path.exists():
                tar.add(dir_path, arcname=d)

        # Einzelne Dateien sichern
        for f in files_to_backup:
            file_path = PROJECT_ROOT / f
            if file_path.exists():
                tar.add(file_path, arcname=f)

    return output_path

def restore_backup_xz(archive_path: Path) -> None:
    """Entpackt ein tar.xz-Archiv und überschreibt die bestehenden Daten."""
    with tarfile.open(archive_path, "r:xz") as tar:
        # Wir entpacken temporär in ein Verzeichnis
        temp_dir = PROJECT_ROOT / "data" / "temp_restore"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        tar.extractall(path=temp_dir)

        # Gefährliche/unerwünschte Pfade filtern
        # Jetzt überschreiben wir die echten Verzeichnisse und Dateien
        for item in temp_dir.iterdir():
            dest_path = PROJECT_ROOT / item.name
            if item.is_dir():
                if dest_path.exists():
                    shutil.rmtree(dest_path)
                shutil.copytree(item, dest_path)
            else:
                if dest_path.exists():
                    os.remove(dest_path)
                shutil.copy(item, dest_path)

        # Temp-Ordner aufräumen
        shutil.rmtree(temp_dir)
