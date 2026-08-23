"""
infrastructure/supabase_sync.py — 2-chiều sync japanese.db với Supabase Storage.
Thay thế infrastructure/drive_sync.py (Google Drive) — cùng chiến lược
merge, chỉ đổi tầng vận chuyển file.

Chiến lược : Last-write-wins theo cột updated_at (giống hệt bản Drive cũ).
Xác thực   : API key (secret/service_role, hoặc publishable/anon nếu bucket
              đã có policy phù hợp) của project Supabase — KHÔNG cần OAuth/
              đăng nhập browser, chỉ cần dán URL + key.
Lưu trữ    : file japanese.db được upload nguyên khối lên 1 Storage bucket
              (mặc định "japanese-db-sync"), rồi merge cục bộ như cũ.

Gọi thẳng Storage REST API bằng httpx thay vì dùng package `supabase`/
`storage3` — thư viện đó có bug xử lý lỗi (một số phản hồi lỗi từ Supabase
không đúng shape mong đợi khiến storage3 tự crash với
"'dict' object has no attribute 'text'", che mất lỗi thật). Gọi thẳng REST
API vừa nhẹ hơn (không kéo theo postgrest/gotrue/realtime không cần dùng),
vừa cho phép hiển thị đúng lỗi gốc từ Supabase để dễ debug.

Yêu cầu:
    pip install httpx

Thiết lập phía Supabase (1 lần):
    1. Tạo project tại https://supabase.com
    2. Vào Storage → tạo bucket mới, ví dụ "japanese-db-sync"
       (Public hay Private đều được — Private an toàn hơn, dùng cùng
       API key để đọc/ghi nên không cần policy đặc biệt nếu bạn dùng
       key loại secret/service_role; nếu dùng publishable/anon key, cần
       bật policy cho phép INSERT/UPDATE/SELECT trên bucket đó.)
    3. Lấy Project URL tại Settings → Data API, và key tại Settings → API Keys.
"""

import sqlite3
import shutil
import os
import logging
import tempfile
from datetime import datetime
from database.db import DB_PATH

logger = logging.getLogger(__name__)

DEFAULT_BUCKET   = "japanese-db-sync"
DEFAULT_FILENAME = "japanese.db"

_TIMEOUT = 30.0


class SupabaseSync:
    """
    Sync 2 chiều giữa local DB và file trên Supabase Storage.

    Params:
        supabase_url    — Project URL, vd: https://xxxx.supabase.co
        supabase_key    — API key (secret/service_role hoặc publishable/anon)
        bucket          — tên bucket Storage (mặc định: japanese-db-sync)
        remote_filename — tên file trong bucket (mặc định: japanese.db)
        progress_cb     — callback(message: str) để cập nhật UI
    """

    def __init__(self, supabase_url: str, supabase_key: str,
                 bucket: str = DEFAULT_BUCKET,
                 remote_filename: str = DEFAULT_FILENAME,
                 progress_cb=None):
        self.supabase_url    = self._clean(supabase_url).rstrip("/")
        self.supabase_key    = self._clean(supabase_key)
        self.bucket           = self._clean(bucket)
        self.remote_filename  = self._clean(remote_filename)
        self.progress_cb     = progress_cb or (lambda msg: None)
        self._storage_base   = f"{self.supabase_url}/storage/v1"
        self._headers = {
            "apikey":        self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
        }

    @staticmethod
    def _clean(s: str) -> str:
        """Bỏ khoảng trắng đầu/cuối và các ký tự vô hình hay dính khi
        copy-paste từ trình duyệt (zero-width space, BOM, non-breaking
        space) — nguyên nhân phổ biến gây lỗi 'Invalid path' dù nhìn
        bằng mắt URL/key có vẻ đúng."""
        if not s:
            return s
        for ch in ("\u200b", "\ufeff", "\xa0"):
            s = s.replace(ch, "")
        return s.strip()

    # ── Public entry point ────────────────────────────────────────────────────

    def sync(self) -> tuple[bool, dict, str]:
        """
        Trả về (success, stats_dict, error_message).
        stats: {pushed, pulled, conflicts_resolved, skipped}
        """
        try:
            return self._run_sync()
        except ImportError as e:
            msg = f"Thiếu thư viện: {e}\nChạy:  pip install httpx"
            logger.error(msg)
            return False, {}, msg
        except Exception as e:
            logger.exception("Sync failed")
            return False, {}, str(e)

    # ── Core sync logic ───────────────────────────────────────────────────────

    def _run_sync(self) -> tuple[bool, dict, str]:
        self._validate_config()

        self._log("🔍 Kiểm tra file trên Supabase...")
        remote_exists = self._remote_exists()

        with tempfile.TemporaryDirectory() as tmp:
            remote_path = os.path.join(tmp, "remote.db")

            if remote_exists:
                self._log("⬇️  Tải DB từ Supabase...")
                self._download(remote_path)
                self._log("🔀 Đang merge dữ liệu...")
                stats = self._merge(local_path=DB_PATH,
                                    remote_path=remote_path)
            else:
                self._log("📭 Chưa có file trên Supabase — sẽ upload lần đầu.")
                stats = {"pushed": 0, "pulled": 0,
                         "conflicts_resolved": 0, "skipped": 0}

            self._log("⬆️  Upload DB đã merge lên Supabase...")
            self._upload(DB_PATH, upsert=remote_exists)

        summary = (f"✅ Sync hoàn tất  |  "
                   f"Đẩy lên: {stats['pushed']}  "
                   f"Kéo về: {stats['pulled']}  "
                   f"Conflict: {stats['conflicts_resolved']}")
        self._log(summary)
        return True, stats, ""

    # ── Supabase Storage REST API (gọi thẳng bằng httpx) ─────────────────────

    def _object_url(self) -> str:
        return f"{self._storage_base}/object/{self.bucket}/{self.remote_filename}"

    def _validate_config(self):
        """Bắt sớm các lỗi cấu hình phổ biến trước khi gọi mạng, vì server
        Supabase có thể trả lỗi khó hiểu ('Invalid path specified in
        request URL') khi Project URL bị dán kèm path thừa (vd .../rest/v1,
        .../dashboard/project/xxx) thay vì chỉ https://xxxx.supabase.co."""
        import re

        if not self.supabase_url or not self.supabase_key:
            raise RuntimeError("Thiếu Project URL hoặc API Key.")

        m = re.match(r"^https://([a-z0-9-]+)\.supabase\.co(/.*)?$", self.supabase_url)
        if not m:
            raise RuntimeError(
                f"Project URL không đúng định dạng: '{self.supabase_url}'.\n"
                "Cần đúng dạng https://xxxxxxxx.supabase.co — không kèm "
                "thêm /rest/v1, /storage/v1, /dashboard/... phía sau.\n"
                "Lấy lại tại Settings → Data API → Project URL.")
        extra_path = m.group(2)
        if extra_path and extra_path not in ("", "/"):
            raise RuntimeError(
                f"Project URL có phần đường dẫn thừa phía sau: '{extra_path}'.\n"
                f"Chỉ dán https://{m.group(1)}.supabase.co (bỏ phần còn lại).")

        if not self.bucket:
            raise RuntimeError("Thiếu tên bucket Storage.")
        if not re.match(r"^[a-zA-Z0-9._-]+$", self.bucket):
            raise RuntimeError(
                f"Tên bucket '{self.bucket}' chứa ký tự không hợp lệ. "
                "Bucket chỉ nên gồm chữ thường, số và dấu gạch ngang.")

    def _remote_exists(self) -> bool:
        import httpx

        # Dùng endpoint list (POST /object/list/<bucket>) với search=filename —
        # tương thích rộng hơn HEAD/info trên mọi version Storage API.
        url = f"{self._storage_base}/object/list/{self.bucket}"
        try:
            resp = httpx.post(
                url,
                headers={**self._headers, "Content-Type": "application/json"},
                json={"prefix": "", "search": self.remote_filename, "limit": 100},
                timeout=_TIMEOUT,
            )
        except httpx.RequestError as e:
            raise RuntimeError(f"Không kết nối được tới Supabase ({url}): {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(self._extract_error(resp, url))

        files = resp.json()
        return any(f.get("name") == self.remote_filename for f in files)

    def _download(self, dest_path: str):
        import httpx

        url = self._object_url()
        try:
            resp = httpx.get(url, headers=self._headers, timeout=_TIMEOUT)
        except httpx.RequestError as e:
            raise RuntimeError(f"Không kết nối được tới Supabase ({url}): {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(self._extract_error(resp, url))

        with open(dest_path, "wb") as f:
            f.write(resp.content)
        logger.info(f"Downloaded {len(resp.content)} bytes from Supabase")

    def _upload(self, src_path: str, upsert: bool):
        import httpx

        with open(src_path, "rb") as f:
            file_bytes = f.read()

        headers = {
            **self._headers,
            "Content-Type": "application/x-sqlite3",
        }
        if upsert:
            headers["x-upsert"] = "true"

        url = self._object_url()
        method = httpx.put if upsert else httpx.post
        try:
            resp = method(url, headers=headers, content=file_bytes, timeout=_TIMEOUT)
        except httpx.RequestError as e:
            raise RuntimeError(f"Không kết nối được tới Supabase ({url}): {e}") from e

        if resp.status_code not in (200, 201):
            raise RuntimeError(self._extract_error(resp, url))
        logger.info(
            f"{'Updated' if upsert else 'Created'} Supabase file {self.remote_filename}")

    @staticmethod
    def _extract_error(resp, url: str = "") -> str:
        """Rút lỗi thật từ response Supabase, không phụ thuộc shape cố định."""
        try:
            data = resp.json()
            if isinstance(data, dict):
                msg = data.get("message") or data.get("error") or data.get("msg") or str(data)
            else:
                msg = str(data)
        except Exception:
            msg = resp.text or f"HTTP {resp.status_code}"
        where = f"\nURL: {url}" if url else ""
        return f"Supabase trả lỗi (HTTP {resp.status_code}): {msg}{where}"

    # ── Merge logic (giống hệt bản Drive cũ — thuần sqlite3, không đụng mạng) ──

    def _merge(self, local_path: str, remote_path: str) -> dict:
        backup = local_path + ".pre_sync"
        shutil.copy2(local_path, backup)
        logger.info(f"Pre-sync backup: {backup}")

        stats = {"pushed": 0, "pulled": 0,
                 "conflicts_resolved": 0, "skipped": 0}

        local_conn  = sqlite3.connect(local_path)
        remote_conn = sqlite3.connect(remote_path)
        local_conn.row_factory  = sqlite3.Row
        remote_conn.row_factory = sqlite3.Row

        try:
            self._merge_cards(local_conn, remote_conn, stats)
            self._merge_decks(local_conn, remote_conn, stats)
            self._merge_deck_cards(local_conn, remote_conn)
            self._merge_radicals(local_conn, remote_conn, stats)
            self._merge_radical_cards(local_conn, remote_conn)
            self._merge_user_decompositions(local_conn, remote_conn, stats)
            self._merge_study_sessions(local_conn, remote_conn, stats)
            local_conn.commit()
        except Exception:
            local_conn.rollback()
            shutil.copy2(backup, local_path)
            raise
        finally:
            local_conn.close()
            remote_conn.close()

        return stats

    def _merge_cards(self, local, remote, stats):
        remote_cards = {r["id"]: dict(r)
                        for r in remote.execute("SELECT * FROM cards")}
        local_cards  = {r["id"]: dict(r)
                        for r in local.execute("SELECT * FROM cards")}

        for rid, rc in remote_cards.items():
            if rid not in local_cards:
                self._insert_card(local, rc)
                stats["pulled"] += 1
            else:
                lc  = local_cards[rid]
                r_ts = self._parse_ts(rc.get("updated_at"))
                l_ts = self._parse_ts(lc.get("updated_at"))
                if r_ts > l_ts:
                    self._update_card(local, rc)
                    stats["conflicts_resolved"] += 1
                elif l_ts > r_ts:
                    stats["pushed"] += 1
                else:
                    stats["skipped"] += 1

        for lid in local_cards:
            if lid not in remote_cards:
                stats["pushed"] += 1

    def _merge_decks(self, local, remote, stats):
        remote_decks = {r["name"]: dict(r)
                        for r in remote.execute("SELECT * FROM decks")}
        local_decks  = {r["name"]: dict(r)
                        for r in local.execute("SELECT * FROM decks")}

        for name, rd in remote_decks.items():
            if name not in local_decks:
                local.execute(
                    "INSERT OR IGNORE INTO decks "
                    "(name, description, color, icon, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (rd["name"], rd.get("description"), rd.get("color"),
                     rd.get("icon"), rd.get("created_at"))
                )
                stats["pulled"] += 1

    def _merge_deck_cards(self, local, remote):
        remote_decks = {r["id"]: r["name"]
                        for r in remote.execute("SELECT id, name FROM decks")}
        local_decks  = {r["name"]: r["id"]
                        for r in local.execute("SELECT id, name FROM decks")}

        for row in remote.execute("SELECT deck_id, card_id FROM deck_cards"):
            deck_name = remote_decks.get(row["deck_id"])
            if not deck_name:
                continue
            local_deck_id = local_decks.get(deck_name)
            if not local_deck_id:
                continue
            if not local.execute(
                    "SELECT 1 FROM cards WHERE id=?", (row["card_id"],)).fetchone():
                continue
            local.execute(
                "INSERT OR IGNORE INTO deck_cards (deck_id, card_id) VALUES (?,?)",
                (local_deck_id, row["card_id"])
            )

    def _merge_radicals(self, local, remote, stats):
        if not self._table_exists(remote, "radicals"):
            return  # remote DB predates the "🧩 Bộ thủ" feature — nothing to pull
        remote_radicals = {r["character"]: dict(r)
                           for r in remote.execute("SELECT * FROM radicals")}
        local_radicals  = {r["character"]: dict(r)
                           for r in local.execute("SELECT * FROM radicals")}

        for character, rr in remote_radicals.items():
            if character not in local_radicals:
                local.execute(
                    "INSERT OR IGNORE INTO radicals "
                    "(character, name, color, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (rr["character"], rr.get("name"), rr.get("color"),
                     rr.get("sort_order", 0), rr.get("created_at"))
                )
                stats["pulled"] += 1

    def _merge_radical_cards(self, local, remote):
        if not self._table_exists(remote, "radical_cards"):
            return
        remote_radicals = {r["id"]: r["character"]
                           for r in remote.execute("SELECT id, character FROM radicals")}
        local_radicals  = {r["character"]: r["id"]
                           for r in local.execute("SELECT character, id FROM radicals")}

        for row in remote.execute("SELECT radical_id, card_id FROM radical_cards"):
            character = remote_radicals.get(row["radical_id"])
            if not character:
                continue
            local_radical_id = local_radicals.get(character)
            if not local_radical_id:
                continue
            if not local.execute(
                    "SELECT 1 FROM cards WHERE id=?", (row["card_id"],)).fetchone():
                continue
            local.execute(
                "INSERT OR IGNORE INTO radical_cards (radical_id, card_id) VALUES (?,?)",
                (local_radical_id, row["card_id"])
            )

    def _merge_user_decompositions(self, local, remote, stats):
        if not self._table_exists(remote, "user_decompositions"):
            return  # remote DB predates the "✏️ Sửa bộ phận" feature
        remote_rows = {r["character"]: dict(r)
                      for r in remote.execute("SELECT * FROM user_decompositions")}
        local_rows  = {r["character"]: dict(r)
                      for r in local.execute("SELECT * FROM user_decompositions")}

        for character, rr in remote_rows.items():
            if character not in local_rows:
                local.execute(
                    "INSERT INTO user_decompositions (character, parts, updated_at) "
                    "VALUES (?,?,?)",
                    (rr["character"], rr["parts"], rr.get("updated_at"))
                )
                stats["pulled"] += 1
            else:
                lr   = local_rows[character]
                r_ts = self._parse_ts(rr.get("updated_at"))
                l_ts = self._parse_ts(lr.get("updated_at"))
                if r_ts > l_ts:
                    local.execute(
                        "UPDATE user_decompositions SET parts=?, updated_at=? WHERE character=?",
                        (rr["parts"], rr.get("updated_at"), character)
                    )
                    stats["conflicts_resolved"] += 1
                elif l_ts > r_ts:
                    stats["pushed"] += 1
                else:
                    stats["skipped"] += 1

    def _merge_study_sessions(self, local, remote, stats):
        local_set = set(
            (r["card_id"], r["result"], r["studied_at"])
            for r in local.execute(
                "SELECT card_id, result, studied_at FROM study_sessions")
        )
        new_count = 0
        for r in remote.execute(
                "SELECT card_id, result, studied_at FROM study_sessions"):
            key = (r["card_id"], r["result"], r["studied_at"])
            if key not in local_set:
                if local.execute(
                        "SELECT 1 FROM cards WHERE id=?",
                        (r["card_id"],)).fetchone():
                    local.execute(
                        "INSERT INTO study_sessions "
                        "(card_id, result, studied_at) VALUES (?,?,?)",
                        (r["card_id"], r["result"], r["studied_at"])
                    )
                    new_count += 1
        if new_count:
            stats["pulled"] += new_count

    # ── Card helpers ──────────────────────────────────────────────────────────

    _CARD_COLS = [
        "id", "type", "character", "reading_on", "reading_kun", "reading_kana",
        "reading_hanviet",
        "romaji", "meaning_vi", "meaning_en", "example_jp", "example_vi",
        "stroke_count", "jlpt_level", "status", "is_favorite", "source",
        "notes", "audio_path", "image_path", "created_at", "updated_at",
        "deleted_at",
    ]

    def _insert_card(self, conn, card):
        cols = self._CARD_COLS
        conn.execute(
            f"INSERT OR IGNORE INTO cards ({', '.join(cols)}) "
            f"VALUES ({', '.join('?'*len(cols))})",
            [card.get(c) for c in cols]
        )

    def _update_card(self, conn, card):
        cols = [c for c in self._CARD_COLS if c != "id"]
        conn.execute(
            f"UPDATE cards SET {', '.join(f'{c}=?' for c in cols)} WHERE id=?",
            [card.get(c) for c in cols] + [card["id"]]
        )

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _table_exists(conn, table_name: str) -> bool:
        """True if `table_name` exists in `conn`'s schema. Guards the
        radicals/radical_cards/user_decompositions merges against an older
        remote DB that predates those features — nothing to pull from a
        table that was never created there."""
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _parse_ts(ts_str) -> datetime:
        if not ts_str:
            return datetime.min
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue
        return datetime.min

    def _log(self, msg: str):
        logger.info(msg)
        self.progress_cb(msg)
