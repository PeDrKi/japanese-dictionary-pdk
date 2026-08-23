"""
reset_db.py — Xoá SẠCH toàn bộ dữ liệu trong database/japanese.db và reset
ID (autoincrement) của mọi bảng về lại bắt đầu từ 1.

Tự động backup file DB hiện tại sang database/japanese.db.bak_YYYYMMDD_HHMMSS
trước khi xoá, để lỡ chạy nhầm vẫn khôi phục lại được.

Chạy:
    python reset_db.py

Sẽ hỏi xác nhận (gõ "XOA") trước khi thực hiện, vì đây là thao tác KHÔNG
thể hoàn tác (ngoại trừ từ file backup).
"""

import sqlite3
import shutil
import os
from datetime import datetime

DB_PATH = os.path.join("database", "japanese.db")

# Thứ tự xoá: bảng phụ thuộc (có khoá ngoại) trước, bảng gốc sau —
# tránh vướng ràng buộc khoá ngoại nếu DB có bật FOREIGN KEY.
TABLES_IN_DELETE_ORDER = [
    "deck_cards",
    "radical_cards",
    "study_sessions",
    "user_decompositions",
    "cards",
    "decks",
    "radicals",
    "deck_categories",
]


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Không tìm thấy {DB_PATH}")
        return

    print("⚠️  Thao tác này sẽ XOÁ TOÀN BỘ dữ liệu (thẻ, bộ thẻ, lịch sử học...)")
    print(f"   trong {DB_PATH} và reset ID về lại từ 1.")
    print("   File hiện tại sẽ được backup lại trước khi xoá.\n")
    confirm = input("Gõ  XOA  để xác nhận: ").strip()
    if confirm != "XOA":
        print("Đã huỷ, không có gì bị xoá.")
        return

    backup_path = DB_PATH + f".bak_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"📦 Đã backup: {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    try:
        existing_tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }

        for table in TABLES_IN_DELETE_ORDER:
            if table in existing_tables:
                conn.execute(f"DELETE FROM {table}")

        # Reset counter autoincrement (cột id INTEGER PRIMARY KEY AUTOINCREMENT)
        # về 0 để bản ghi tiếp theo bắt đầu lại từ id = 1.
        if "sqlite_sequence" in existing_tables:
            conn.execute("DELETE FROM sqlite_sequence")

        conn.commit()
        conn.execute("VACUUM")
        print("✅ Đã xoá sạch dữ liệu và reset ID về 1.")
    except Exception as e:
        conn.rollback()
        print(f"❌ Lỗi, đã rollback: {e}")
        print(f"   DB gốc vẫn còn nguyên tại {backup_path} nếu cần khôi phục.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
