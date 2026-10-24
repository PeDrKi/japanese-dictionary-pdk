"""
infrastructure/backup.py — Database backup and restore.
Backup: snapshots japanese.db (SQLite Backup API, an toàn với WAL) into a timestamped .zip alongside
        settings.json (đã loại bỏ khoá Supabase)
Restore: extracts .zip and replaces japanese.db
Moved from utils/ (Stage: utils/ cleanup) since this does real file I/O.
"""
import os
import json
import shutil
import sqlite3
import tempfile
import zipfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "database")
_DB_PATH      = os.path.normpath(os.path.join(_DB_DIR, "japanese.db"))
_SETTINGS_PATH= os.path.normpath(os.path.join(_DB_DIR, "..", "settings.json"))


# Các khoá chứa thông tin đăng nhập — KHÔNG đưa vào file backup (backup hay được gửi/lưu lên đám mây)
_SECRET_SETTINGS = ("supabase_key", "supabase_url", "supabase_bucket", "supabase_db_filename",
                    "cloud_url", "cloud_key", "cloud_email", "cloud_refresh_token")


def _sqlite_snapshot(src_path: str, dest_path: str):
    """Chụp bản sao NHẤT QUÁN bằng SQLite Backup API. Chép file .db thô là sai khi chế độ WAL
    đang bật: dữ liệu mới nhất còn nằm trong file -wal nên bản chép thiếu (có thể rỗng)."""
    src = sqlite3.connect(src_path)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _sanitized_settings_json() -> str | None:
    if not os.path.exists(_SETTINGS_PATH):
        return None
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in _SECRET_SETTINGS:
            data.pop(k, None)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        return None


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

        with tempfile.TemporaryDirectory() as tmp, \
                zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
            snap = os.path.join(tmp, "japanese.db")
            _sqlite_snapshot(_DB_PATH, snap)
            zf.write(snap, "japanese.db")
            settings_json = _sanitized_settings_json()
            if settings_json is not None:
                zf.writestr("settings.json", settings_json)

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

    # Safety backup of current DB before overwriting (bằng Backup API, không chép file thô)
    safety_path = _DB_PATH + ".before_restore"
    try:
        if os.path.exists(_DB_PATH):
            if os.path.exists(safety_path):
                os.remove(safety_path)
            _sqlite_snapshot(_DB_PATH, safety_path)
    except Exception as e:
        return False, f"Không thể tạo backup an toàn: {e}"

    try:
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path, "r") as zf:
            extracted = os.path.join(tmp, "restore.db")
            with zf.open("japanese.db") as src, open(extracted, "wb") as out:
                shutil.copyfileobj(src, out)

            # Kiểm tra file backup trước khi động vào DB đang dùng
            chk = sqlite3.connect(extracted)
            try:
                ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
                has_cards = chk.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cards'").fetchone()
            finally:
                chk.close()
            if ok != "ok" or not has_cards:
                return False, "File backup bị hỏng hoặc không phải database của app — chưa thay đổi gì."

            # Ghi đè nội dung DB đang dùng bằng Backup API (đi qua cơ chế khoá/WAL của SQLite).
            # KHÔNG thay file thô: file -wal cũ sẽ bị áp lên bản khôi phục khi app thoát và
            # làm bản khôi phục bị hủy (hoặc hỏng).
            src = sqlite3.connect(extracted)
            try:
                dst = sqlite3.connect(_DB_PATH, timeout=10)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()

            # DB khôi phục mang theo mốc/bản gốc đồng bộ CŨ → nếu để nguyên, lần sync tới sẽ ghi đè bản khôi phục bằng trạng thái hiện tại
            # trên máy chủ (vd thẻ đã xoá sau backup lại bị xoá tiếp). Đặt lại để bản khôi phục được coi là "chưa gửi".
            try:
                from infrastructure.cloud_sync import reset_sync_state
                reset_sync_state(_DB_PATH)
            except Exception as e:
                logger.warning(f"reset_sync_state after restore failed: {e}")

            if "settings.json" in zf.namelist():
                _restore_settings(json.loads(zf.read("settings.json").decode("utf-8")))

        logger.info(f"Restored from: {zip_path}")
        return True, (
            f"Khôi phục thành công!\n"
            f"Backup an toàn của DB cũ: {os.path.basename(safety_path)}\n\n"
            f"Hãy khởi động lại app để áp dụng."
        )
    except Exception as e:
        # Backup API ghi theo giao dịch nên lỗi giữa chừng không để DB nửa vời; vẫn thử trả về bản an toàn
        try:
            if os.path.exists(safety_path):
                _sqlite_snapshot(safety_path, _DB_PATH)
        except Exception:
            pass
        logger.error(f"Restore failed: {e}")
        return False, f"Khôi phục thất bại: {e}"


def _restore_settings(restored: dict):
    """Khôi phục cài đặt giao diện nhưng GIỮ NGUYÊN cấu hình Supabase hiện tại của máy này."""
    current = {}
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            current = json.load(f)
    except Exception:
        pass
    merged = {k: v for k, v in restored.items() if k not in _SECRET_SETTINGS}
    for k in _SECRET_SETTINGS:
        if k in current:
            merged[k] = current[k]
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


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
