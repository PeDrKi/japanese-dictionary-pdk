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
import os
import logging
import tempfile
from datetime import datetime
from database.db import DB_PATH, init_db as _init_db_schema

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
        remote_exists, server_date = self._remote_exists()
        self._check_clock_skew(server_date)

        self._log("🔒 Xin khóa đồng bộ (tránh 2 máy sync cùng lúc)...")
        self._acquire_lock()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                remote_path = os.path.join(tmp, "remote.db")

                if remote_exists:
                    self._log("⬇️  Tải DB từ Supabase...")
                    self._download(remote_path)
                    # Bản trên Supabase có thể là snapshot cũ (upload từ 1
                    # lần sync trước, lúc app chưa có cột/migration mới
                    # nhất) — nâng cấp schema của nó lên mới nhất trước khi
                    # merge, tránh lỗi kiểu "no such column: ...".
                    _init_db_schema(db_path=remote_path)
                    self._log("🔀 Đang merge dữ liệu...")
                    stats = self._merge(local_path=DB_PATH,
                                        remote_path=remote_path)
                else:
                    self._log("📭 Chưa có file trên Supabase — sẽ upload lần đầu.")
                    stats = {"pushed": 0, "pulled": 0,
                             "conflicts_resolved": 0, "skipped": 0,
                             "id_collisions": 0}

                self._log("⬆️  Upload DB đã merge lên Supabase...")
                self._upload(DB_PATH, upsert=remote_exists)
        finally:
            self._release_lock()

        summary = (f"✅ Sync hoàn tất  |  "
                   f"Đẩy lên: {stats['pushed']}  "
                   f"Kéo về: {stats['pulled']}  "
                   f"Conflict: {stats['conflicts_resolved']}")
        if stats.get("id_collisions"):
            summary += f"\n⚠️ Phát hiện {stats['id_collisions']} trường hợp trùng ID — đã tự thêm thành mục mới, không mất dữ liệu, nhưng bạn nên kiểm tra lại (xem log ở trên) để dọn trùng lặp nếu cần."
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

    def _remote_exists(self) -> tuple:
        """Trả về (exists: bool, server_date: datetime|None). server_date
        lấy từ header 'Date' của response — dùng để phát hiện đồng hồ máy
        local bị lệch trước khi merge (updated_at sai lệch làm merge sai)."""
        import httpx
        from email.utils import parsedate_to_datetime

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

        server_date = None
        date_header = resp.headers.get("date")
        if date_header:
            try:
                server_date = parsedate_to_datetime(date_header)
            except Exception:
                server_date = None

        files = resp.json()
        exists = any(f.get("name") == self.remote_filename for f in files)
        return exists, server_date

    def _check_clock_skew(self, server_date, max_skew_seconds: int = 300):
        """Chặn sync sớm nếu đồng hồ hệ thống local lệch quá nhiều so với
        giờ server — vì toàn bộ merge dựa vào so sánh updated_at lấy từ
        giờ local, đồng hồ sai sẽ khiến bản mới bị coi là cũ (hoặc ngược
        lại) một cách âm thầm."""
        if server_date is None:
            return  # Không lấy được giờ server (hiếm) — bỏ qua, không chặn sync.

        from datetime import timezone
        local_now = datetime.now(timezone.utc)
        sd = server_date if server_date.tzinfo else server_date.replace(tzinfo=timezone.utc)
        diff = abs((local_now - sd).total_seconds())
        if diff > max_skew_seconds:
            minutes = round(diff / 60, 1)
            raise RuntimeError(
                f"Đồng hồ hệ thống máy bạn đang lệch khoảng {minutes} phút so với "
                "giờ chuẩn. Sync bị dừng để tránh merge sai (dữ liệu mới có thể bị "
                "hiểu nhầm là cũ hơn). Hãy bật đồng bộ giờ tự động (Windows: Settings "
                "→ Time & Language → 'Set time automatically') rồi thử lại.")

    # ── Khóa sync — hạn chế 2 thiết bị sync cùng lúc chồng lên nhau ──────────

    _LOCK_FILENAME = "sync.lock"
    _LOCK_MAX_AGE_SECONDS = 5 * 60

    def _lock_url(self) -> str:
        return f"{self._storage_base}/object/{self.bucket}/{self._LOCK_FILENAME}"

    def _acquire_lock(self):
        """Best-effort: kiểm tra + tạo file khóa nhỏ trên Supabase trước
        khi sync. Không phải khóa phân tán tuyệt đối (vẫn có khe hở nhỏ
        nếu 2 máy bấm Sync đúng cùng 1 khoảnh khắc), nhưng đủ ngăn trường
        hợp phổ biến nhất: 2 máy sync chồng lên nhau trong vài phút.
        Khóa tự hết hạn sau 5 phút nên không bao giờ bị kẹt vĩnh viễn nếu
        app crash giữa chừng."""
        import httpx
        import socket

        device = socket.gethostname() or "thiết bị không rõ tên"
        url = self._lock_url()

        try:
            resp = httpx.get(url, headers=self._headers, timeout=_TIMEOUT)
        except httpx.RequestError:
            return  # Lỗi mạng sẽ lộ rõ ở bước tiếp theo, không chặn ở đây.

        if resp.status_code == 200:
            owner, age = "không rõ", 0
            try:
                content = resp.content.decode("utf-8", errors="ignore")
                owner, _, ts_str = content.partition("|")
                lock_time = datetime.fromisoformat(ts_str)
                age = (datetime.utcnow() - lock_time).total_seconds()
            except Exception:
                age = 0  # Không đọc được nội dung khóa -> thận trọng, coi như còn mới
            if age < self._LOCK_MAX_AGE_SECONDS:
                remain = int(self._LOCK_MAX_AGE_SECONDS - age)
                raise RuntimeError(
                    f"Thiết bị khác ({owner}) có thể đang sync (khóa tạo "
                    f"{int(age)} giây trước). Đợi khoảng {remain} giây rồi thử lại "
                    "để tránh 2 máy ghi đè lẫn nhau.")

        body = f"{device}|{datetime.utcnow().isoformat()}".encode("utf-8")
        headers = {**self._headers, "Content-Type": "text/plain", "x-upsert": "true"}
        try:
            r = httpx.post(url, headers=headers, content=body, timeout=_TIMEOUT)
            if r.status_code not in (200, 201):
                httpx.put(url, headers=headers, content=body, timeout=_TIMEOUT)
        except httpx.RequestError:
            pass  # Không tạo được khóa thì thôi, không chặn sync vì lý do này.

    def _release_lock(self):
        import httpx
        try:
            httpx.request(
                "DELETE", f"{self._storage_base}/object/{self.bucket}",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"prefixes": [self._LOCK_FILENAME]}, timeout=_TIMEOUT)
        except httpx.RequestError:
            pass  # Khóa sẽ tự hết hạn sau 5 phút dù xóa lỗi.

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

        # Không đọc trực tiếp byte thô của src_path (file DB đang được ứng
        # dụng desktop giữ kết nối mở) — trên Windows việc mở file thô để
        # đọc trong lúc SQLite đang khoá nó có thể ném lỗi hệ điều hành khó
        # hiểu kiểu "[Errno 22] Invalid argument". Dùng đúng API Backup của
        # SQLite để lấy 1 bản snapshot nhất quán, an toàn dù file đang mở ở
        # nơi khác, rồi upload từ bản snapshot đó.
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = os.path.join(tmp, "snapshot.db")
            self._sqlite_backup(src_path, snapshot)
            with open(snapshot, "rb") as f:
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
    def _sqlite_backup(src_path: str, dest_path: str):
        """Snapshot src_path -> dest_path bằng SQLite Backup API (chuẩn,
        an toàn với nhiều tiến trình/kết nối đang mở cùng file — không như
        copy file thô bằng shutil/open() vốn có thể vướng khoá file của hệ
        điều hành, đặc biệt trên Windows, hoặc chụp phải trạng thái nửa
        vời nếu file đang được ghi dở)."""
        src = sqlite3.connect(src_path)
        try:
            dest = sqlite3.connect(dest_path)
            try:
                src.backup(dest)
            finally:
                dest.close()
        finally:
            src.close()

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
        self._sqlite_backup(local_path, backup)
        logger.info(f"Pre-sync backup: {backup}")

        stats = {"pushed": 0, "pulled": 0,
                 "conflicts_resolved": 0, "skipped": 0, "id_collisions": 0}

        local_conn  = sqlite3.connect(local_path)
        remote_conn = sqlite3.connect(remote_path)
        local_conn.row_factory  = sqlite3.Row
        remote_conn.row_factory = sqlite3.Row

        try:
            self._merge_table(local_conn, remote_conn, "cards", self._CARD_COLS,
                              immutable_cols=["type", "character", "created_at"],
                              stats=stats, label="thẻ")
            self._merge_table(local_conn, remote_conn, "decks", self._DECK_COLS,
                              immutable_cols=["created_at"],
                              stats=stats, label="bộ thẻ")
            self._merge_deck_cards(local_conn, remote_conn)
            if self._table_exists(remote_conn, "radicals"):
                self._merge_table(local_conn, remote_conn, "radicals", self._RADICAL_COLS,
                                  immutable_cols=["created_at"],
                                  stats=stats, label="bộ thủ")
                self._merge_radical_cards(local_conn, remote_conn)
            self._merge_user_decompositions(local_conn, remote_conn, stats)
            self._merge_study_sessions(local_conn, remote_conn, stats)
            local_conn.commit()
        except Exception:
            local_conn.rollback()
            local_conn.close()
            remote_conn.close()
            # Khôi phục từ backup bằng Backup API (an toàn hơn ghi đè file
            # thô) — _sqlite_backup tự mở kết nối riêng tới local_path.
            self._sqlite_backup(backup, local_path)
            raise
        else:
            local_conn.close()
            remote_conn.close()

        return stats

    # ── Merge theo id với xóa mềm + phát hiện trùng ID ───────────────────────
    #
    # "Trùng ID" = 2 thiết bị độc lập tạo ra 2 bản ghi KHÁC NHAU nhưng vô
    # tình được gán cùng 1 id (dễ xảy ra nhất sau khi chạy reset_db.py trên
    # 1 máy mà chưa sync các máy còn lại). Nhận diện bằng cách so sánh các
    # cột "bất biến" (immutable_cols — những giá trị đáng lẽ không đổi sau
    # khi tạo, vd created_at) giữa 2 bản ghi cùng id: khác nhau -> chắc
    # chắn là 2 bản ghi khác nhau, KHÔNG phải 1 bản ghi được sửa. Thay vì
    # ghi đè âm thầm (mất dữ liệu), bản ghi "thua" được thêm vào như một
    # dòng MỚI (id khác) để giữ lại cả 2, kèm cảnh báo cho người dùng.

    def _merge_table(self, local, remote, table, cols, immutable_cols, stats, label):
        remote_rows = {r["id"]: dict(r) for r in remote.execute(f"SELECT * FROM {table}")}
        local_rows  = {r["id"]: dict(r) for r in local.execute(f"SELECT * FROM {table}")}

        for rid, rr in remote_rows.items():
            if rid not in local_rows:
                self._insert_row(local, table, cols, rr)
                stats["pulled"] += 1
                continue

            lr = local_rows[rid]
            if any(lr.get(c) != rr.get(c) for c in immutable_cols):
                if self._insert_row(local, table, cols, rr, as_new=True):
                    stats["id_collisions"] += 1
                    name = rr.get("character") or rr.get("name") or f"id={rid}"
                    self._log(f"⚠️ Trùng ID #{rid} ở {label} ('{name}') — "
                             f"đã thêm bản từ Supabase làm mục MỚI, giữ nguyên "
                             f"cả 2 bản để không mất dữ liệu.")
                continue

            r_ts = self._parse_ts(rr.get("updated_at"))
            l_ts = self._parse_ts(lr.get("updated_at"))
            if r_ts > l_ts:
                self._update_row(local, table, cols, rr)
                stats["conflicts_resolved"] += 1
            elif l_ts > r_ts:
                stats["pushed"] += 1
            else:
                stats["skipped"] += 1

        for lid in local_rows:
            if lid not in remote_rows:
                stats["pushed"] += 1

    @staticmethod
    def _insert_row(conn, table, cols, row, as_new=False) -> bool:
        """Chèn 1 dòng. as_new=True bỏ qua cột id (để SQLite tự cấp id mới)
        — dùng khi giải quyết trùng ID. Trả về False (bỏ qua, không raise)
        nếu vẫn đụng ràng buộc UNIQUE khác (vd trùng tên/ký tự) — hiếm khi
        xảy ra nhưng không được để làm hỏng cả phiên sync."""
        insert_cols = [c for c in cols if c != "id"] if as_new else cols
        try:
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({', '.join(insert_cols)}) "
                f"VALUES ({', '.join('?' * len(insert_cols))})",
                [row.get(c) for c in insert_cols]
            )
            return True
        except sqlite3.IntegrityError as e:
            logger.warning(f"Bỏ qua bản ghi xung đột khi merge {table}: {e}")
            return False

    @staticmethod
    def _update_row(conn, table, cols, row):
        update_cols = [c for c in cols if c != "id"]
        conn.execute(
            f"UPDATE {table} SET {', '.join(f'{c}=?' for c in update_cols)} WHERE id=?",
            [row.get(c) for c in update_cols] + [row["id"]]
        )

    # ── Bảng liên kết (deck_cards / radical_cards) ────────────────────────────
    #
    # Không merge theo id riêng của bảng liên kết (chỉ có ý nghĩa nội bộ 1
    # DB) — thay vào đó dịch deck_id/radical_id phía remote sang id tương
    # ứng ở local qua tên/ký tự (decks.name, radicals.character đều UNIQUE),
    # rồi so khớp theo cặp tự nhiên (deck_id, card_id)/(radical_id, card_id)
    # + so sánh updated_at để việc gỡ 1 thẻ khỏi deck/bộ cũng đồng bộ đúng.

    def _merge_deck_cards(self, local, remote):
        remote_decks = {r["id"]: r["name"]
                        for r in remote.execute("SELECT id, name FROM decks")}
        local_decks  = {r["name"]: r["id"]
                        for r in local.execute("SELECT id, name FROM decks")}

        for row in remote.execute(
                "SELECT deck_id, card_id, added_at, updated_at, deleted_at FROM deck_cards"):
            deck_name = remote_decks.get(row["deck_id"])
            if not deck_name:
                continue
            local_deck_id = local_decks.get(deck_name)
            if not local_deck_id:
                continue
            if not local.execute(
                    "SELECT 1 FROM cards WHERE id=?", (row["card_id"],)).fetchone():
                continue

            existing = local.execute(
                "SELECT updated_at FROM deck_cards WHERE deck_id=? AND card_id=?",
                (local_deck_id, row["card_id"])
            ).fetchone()
            if existing is None:
                local.execute(
                    "INSERT OR IGNORE INTO deck_cards "
                    "(deck_id, card_id, added_at, updated_at, deleted_at) VALUES (?,?,?,?,?)",
                    (local_deck_id, row["card_id"], row["added_at"],
                     row["updated_at"], row["deleted_at"])
                )
            elif self._parse_ts(row["updated_at"]) > self._parse_ts(existing["updated_at"]):
                local.execute(
                    "UPDATE deck_cards SET updated_at=?, deleted_at=? "
                    "WHERE deck_id=? AND card_id=?",
                    (row["updated_at"], row["deleted_at"], local_deck_id, row["card_id"])
                )

    def _merge_radical_cards(self, local, remote):
        if not self._table_exists(remote, "radical_cards"):
            return
        remote_radicals = {r["id"]: r["character"]
                           for r in remote.execute("SELECT id, character FROM radicals")}
        local_radicals  = {r["character"]: r["id"]
                           for r in local.execute("SELECT character, id FROM radicals")}

        for row in remote.execute(
                "SELECT radical_id, card_id, added_at, updated_at, deleted_at FROM radical_cards"):
            character = remote_radicals.get(row["radical_id"])
            if not character:
                continue
            local_radical_id = local_radicals.get(character)
            if not local_radical_id:
                continue
            if not local.execute(
                    "SELECT 1 FROM cards WHERE id=?", (row["card_id"],)).fetchone():
                continue

            existing = local.execute(
                "SELECT updated_at FROM radical_cards WHERE radical_id=? AND card_id=?",
                (local_radical_id, row["card_id"])
            ).fetchone()
            if existing is None:
                local.execute(
                    "INSERT OR IGNORE INTO radical_cards "
                    "(radical_id, card_id, added_at, updated_at, deleted_at) VALUES (?,?,?,?,?)",
                    (local_radical_id, row["card_id"], row["added_at"],
                     row["updated_at"], row["deleted_at"])
                )
            elif self._parse_ts(row["updated_at"]) > self._parse_ts(existing["updated_at"]):
                local.execute(
                    "UPDATE radical_cards SET updated_at=?, deleted_at=? "
                    "WHERE radical_id=? AND card_id=?",
                    (row["updated_at"], row["deleted_at"], local_radical_id, row["card_id"])
                )

    def _merge_user_decompositions(self, local, remote, stats):
        if not self._table_exists(remote, "user_decompositions"):
            return  # remote DB predates the "✏️ Sửa bộ phận" feature
        remote_rows = {r["character"]: dict(r)
                      for r in remote.execute("SELECT * FROM user_decompositions")}
        local_rows  = {r["character"]: dict(r)
                      for r in local.execute("SELECT * FROM user_decompositions")}

        # character là PRIMARY KEY thật (không phải id tự tăng) nên không
        # có rủi ro trùng ID kiểu 2 thiết bị tạo độc lập — không cần bước
        # phát hiện collision ở bảng này.
        for character, rr in remote_rows.items():
            if character not in local_rows:
                local.execute(
                    "INSERT INTO user_decompositions (character, parts, updated_at, deleted_at) "
                    "VALUES (?,?,?,?)",
                    (rr["character"], rr["parts"], rr.get("updated_at"), rr.get("deleted_at"))
                )
                stats["pulled"] += 1
            else:
                lr   = local_rows[character]
                r_ts = self._parse_ts(rr.get("updated_at"))
                l_ts = self._parse_ts(lr.get("updated_at"))
                if r_ts > l_ts:
                    local.execute(
                        "UPDATE user_decompositions SET parts=?, updated_at=?, deleted_at=? "
                        "WHERE character=?",
                        (rr["parts"], rr.get("updated_at"), rr.get("deleted_at"), character)
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

    # ── Column lists dùng bởi _merge_table ────────────────────────────────────

    _CARD_COLS = [
        "id", "type", "character", "reading_on", "reading_kun", "reading_kana",
        "reading_hanviet",
        "romaji", "meaning_vi", "meaning_en", "example_jp", "example_vi",
        "stroke_count", "jlpt_level", "status", "is_favorite", "source",
        "notes", "audio_path", "image_path", "created_at", "updated_at",
        "deleted_at",
    ]

    _DECK_COLS = [
        "id", "name", "description", "color", "icon", "category_id",
        "created_at", "updated_at", "deleted_at",
    ]

    _RADICAL_COLS = [
        "id", "character", "name", "color", "sort_order",
        "created_at", "updated_at", "deleted_at",
    ]

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
