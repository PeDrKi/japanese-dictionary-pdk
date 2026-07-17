"""
infrastructure/backup.py — Database backup and restore.
Backup: copies japanese.db into a timestamped .zip alongside settings.json
Restore: extracts .zip and replaces japanese.db
Moved from utils/ (Stage: utils/ cleanup) since this does real file I/O.
"""
import os
import shutil
import zipfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "database")
_DB_PATH      = os.path.normpath(os.path.join(_DB_DIR, "japanese.db"))
_SETTINGS_PATH= os.path.normpath(os.path.join(_DB_DIR, "..", "settings.json"))


def create_backup(dest_dir: str) -> tuple[str, str]:
    """
    Create a .zip backup of the database (+ settings).
    Returns (filepath, error). error is empty on success.
    """
    if not os.path.exists(_DB_PATH):
        return "", "Không tìm thấy file database."
    try:
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"japanese_backup_{ts}.zip"
        filepath = os.path.join(dest_dir, filename)

        with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(_DB_PATH,      "japanese.db")
            if os.path.exists(_SETTINGS_PATH):
                zf.write(_SETTINGS_PATH, "settings.json")

        size_kb = os.path.getsize(filepath) // 1024
        logger.info(f"Backup created: {filepath} ({size_kb} KB)")
        return filepath, ""
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return "", str(e)


def restore_backup(zip_path: str) -> tuple[bool, str]:
    """
    Restore database from a .zip backup file.
    Creates a safety backup of the current DB first.
    Returns (success, message).
    """
    if not os.path.exists(zip_path):
        return False, "File backup không tồn tại."

    # Validate zip contains japanese.db
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if "japanese.db" not in names:
                return False, "File zip không chứa 'japanese.db'."
    except zipfile.BadZipFile:
        return False, "File không phải định dạng .zip hợp lệ."
    except Exception as e:
        return False, f"Không thể đọc file: {e}"

    # Safety backup of current DB before overwriting
    safety_path = _DB_PATH + ".before_restore"
    try:
        if os.path.exists(_DB_PATH):
            shutil.copy2(_DB_PATH, safety_path)
    except Exception as e:
        return False, f"Không thể tạo backup an toàn: {e}"

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extract("japanese.db", os.path.dirname(_DB_PATH))
            if "settings.json" in zf.namelist():
                zf.extract("settings.json",
                           os.path.dirname(_SETTINGS_PATH))

        logger.info(f"Restored from: {zip_path}")
        return True, (
            f"Khôi phục thành công!\n"
            f"Backup an toàn của DB cũ: {os.path.basename(safety_path)}\n\n"
            f"Hãy khởi động lại app để áp dụng."
        )
    except Exception as e:
        # Try to roll back
        try:
            if os.path.exists(safety_path):
                shutil.copy2(safety_path, _DB_PATH)
        except Exception:
            pass
        logger.error(f"Restore failed: {e}")
        return False, f"Khôi phục thất bại: {e}"


def list_backups(directory: str) -> list[dict]:
    """Return sorted list of backup files in a directory."""
    result = []
    if not os.path.isdir(directory):
        return result
    for fname in os.listdir(directory):
        if fname.startswith("japanese_backup_") and fname.endswith(".zip"):
            fpath = os.path.join(directory, fname)
            stat  = os.stat(fpath)
            result.append({
                "filename": fname,
                "path":     fpath,
                "size_kb":  stat.st_size // 1024,
                "mtime":    datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return sorted(result, key=lambda x: x["mtime"], reverse=True)
