"""
infrastructure/cloud_sync.py — đồng bộ japanese.db (SQLite) với CÙNG cơ sở dữ liệu Supabase Postgres
mà bản web dùng (schema.sql phiên bản 3). Thay cho cách cũ (upload nguyên file .db lên Storage).

Vì sao đổi:
  • Bản cũ ghi đè cả hàng theo giờ máy ("naive", không múi giờ) → 2 máy sửa cùng lúc là mất 1 bên,
    xóa / ★ / tiến độ ôn không sang máy khác, và khóa Storage phải mở cho khoá anon (ai có khoá đều đọc/ghi được).
  • Bản mới: đăng nhập bằng tài khoản Supabase (email + mật khẩu, y như web), Row Level Security chỉ cho
    thấy dữ liệu của chính bạn; web và desktop thấy CÙNG dữ liệu.

Cách hoạt động (offline-first — app vẫn dùng SQLite cục bộ, đồng bộ khi có mạng):
  • Mỗi hàng cards/decks/radicals lưu `server_version` + `base_json` (bản chụp hàng trên máy chủ lần đồng bộ trước).
    Gửi lên bằng "so sánh-và-ghi" (PATCH ... version=eq.N): chỉ gửi những TRƯỜNG bạn đã sửa.
    Nếu ai đó đã sửa trước → gộp 3 chiều theo trường; cùng 1 trường khác giá trị → bản MỚI HƠN thắng
    và giá trị thua được ghi vào bảng sync_conflicts (SQLite cục bộ) + báo trong kết quả (bản web thì hỏi bạn chọn).
  • Ôn tập: gửi từng lượt qua hàm server `log_study` (tính SRS nguyên tử, không ghi đè lẫn nhau, gửi lại không bị tính 2 lần).
    Tiến độ SRS của thẻ KHÔNG bao giờ bị gửi như một lần sửa thẻ.
  • Danh mục / liên kết thẻ-bộ / tách bộ: người ghi sau thắng (giống web).
  • Giờ: máy chủ đặt updated_at; giờ cục bộ chỉ được đổi sang UTC khi gửi, nên không còn lỗi múi giờ.

Chỉ cần: pip install httpx
"""
import json
import logging
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from infrastructure.id_gen import uuid7

logger = logging.getLogger(__name__)

SCHEMA_MIN = 12
PAGE = 1000
CURSOR_OVERLAP = timedelta(minutes=2)       # chồng lấn khi kéo theo updated_at (an toàn vì mọi thao tác đều idempotent)
SESSION_OVERLAP = timedelta(days=14)        # lượt ôn nhập muộn từ máy offline

CARD_FIELDS = ["type", "character", "reading_on", "reading_kun", "reading_kana", "reading_hanviet", "romaji",
               "meaning_vi", "meaning_en", "example_jp", "example_vi", "stroke_count", "jlpt_level",
               "is_favorite", "source", "notes", "pos", "deleted_at"]
SRS_FIELDS = ["srs_interval", "srs_ease", "srs_due_date", "study_count", "status"]   # máy chủ tính; chỉ gửi lúc tạo, sau đó chỉ kéo về
DECK_FIELDS = ["name", "description", "color", "icon", "category_id", "deleted_at"]
RAD_FIELDS = ["character", "name", "color", "sort_order", "deleted_at"]
GRAMMAR_FIELDS = ["title", "meaning_vi", "structure", "explanation", "examples", "jlpt_level"]
TRANS_FIELDS = ["title", "jp", "vi", "note", "jlpt_level", "glossary"]
CONJ_FORM_FIELDS = ["name", "kind", "hidden", "sort_order"]
CONJ_VERB_FIELDS = ["masu", "meaning_vi", "grp", "sort_order"]
FIELDS = {"cards": CARD_FIELDS, "decks": DECK_FIELDS, "radicals": RAD_FIELDS, "grammar_points": GRAMMAR_FIELDS,
          "translations": TRANS_FIELDS, "conj_forms": CONJ_FORM_FIELDS, "conj_verbs": CONJ_VERB_FIELDS}
# Bảng có version (gộp theo trường). Thứ tự quan trọng: cột / động từ phải lên trước các ô (conj_cells).
VERSIONED = ("decks", "radicals", "cards", "grammar_points", "translations", "conj_forms", "conj_verbs")
HARD_DELETE_TABLES = ("cards", "decks", "radicals", "deck_categories", "grammar_points", "translations", "conj_forms", "conj_verbs")
UNIQUE_KEY = {"decks": "name", "radicals": "character"}          # chỉ tính hàng chưa xóa
CARD_TYPES = ("kanji", "hiragana", "katakana", "vocab")
CARD_STATUSES = ("new", "learning", "known")
CARD_POS = ("noun", "verb", "verb1", "verb2", "verb3", "adj_i", "adj_na",
            "pronoun", "particle", "adverb", "conjunction", "interjection")
# bảng con tham chiếu id (để đổi id khi gộp trùng): table → [(bảng con, cột)]
CHILDREN = {
    "decks": [("deck_cards", "deck_id")],
    "radicals": [("radical_cards", "radical_id")],
    "cards": [("deck_cards", "card_id"), ("radical_cards", "card_id"), ("study_sessions", "card_id")],
    "deck_categories": [("decks", "category_id")],
}


_SYNC_LOCK = threading.Lock()   # chỉ cho 1 lần đồng bộ chạy tại một thời điểm (hộp thoại Sync / tự đồng bộ khi mở / khi thoát)


class CloudSyncError(Exception):
    pass


class AccountMismatch(CloudSyncError):
    """Database cục bộ đang gắn với tài khoản/máy chủ khác — không tự động đồng bộ để khỏi trộn dữ liệu hai tài khoản."""


# ── Thời gian ────────────────────────────────────────────────────────────────

_FRAC = re.compile(r"\.(\d+)")


def _parse_dt(s: str) -> datetime:
    s = str(s).strip().replace("Z", "+00:00").replace(" ", "T", 1)
    s = _FRAC.sub(lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    return datetime.fromisoformat(s)


def local_to_utc(s):
    """'YYYY-MM-DD HH:MM:SS' (giờ máy) → ISO UTC. None giữ nguyên."""
    if not s:
        return None
    dt = _parse_dt(s)
    if dt.tzinfo is None:
        dt = dt.astimezone()          # naive = giờ địa phương
    return dt.astimezone(timezone.utc).isoformat()


def utc_to_local(s):
    """ISO (có múi giờ) → 'YYYY-MM-DD HH:MM:SS' giờ máy."""
    if not s:
        return None
    dt = _parse_dt(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _aware(s):
    if not s:
        return None
    dt = _parse_dt(s)
    return dt if dt.tzinfo else dt.astimezone()


# ── So sánh trường ───────────────────────────────────────────────────────────

def _norm(v):
    return None if v is None or v == "" else v


def same(field, a, b):
    if field == "deleted_at":                    # chỉ quan tâm "đã xóa hay chưa" (độ phân giải thời gian khác nhau)
        return (_norm(a) is None) == (_norm(b) is None)
    a, b = _norm(a), _norm(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return a == b


def diff_fields(base, cur, fields):
    return {f: _norm(cur.get(f)) for f in fields if not same(f, base.get(f), cur.get(f))}


def plan_merge(base, changes, remote):
    apply, conflicts = {}, []
    for f, mine in changes.items():
        if same(f, remote.get(f), mine):
            continue
        if same(f, remote.get(f), base.get(f)):
            apply[f] = mine
        else:
            conflicts.append((f, base.get(f), mine, remote.get(f)))
    return apply, conflicts


# ── Xác thực ─────────────────────────────────────────────────────────────────

class PasswordAuth:
    """Đăng nhập Supabase Auth (GoTrue) bằng email + mật khẩu, rồi giữ phiên bằng refresh token."""

    def __init__(self, url, anon_key, email=None, password=None, refresh_token=None,
                 on_refresh_token=None, timeout=30.0):
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.email, self.password = email, password
        self.refresh_token = refresh_token
        self.on_refresh_token = on_refresh_token
        self.timeout = timeout
        self._access = None
        self._exp = 0
        self.user_id = None

    def _grant(self, grant, body):
        import httpx
        try:
            r = httpx.post(f"{self.url}/auth/v1/token", params={"grant_type": grant}, json=body,
                           headers={"apikey": self.anon_key}, timeout=self.timeout)
        except httpx.RequestError as e:
            raise CloudSyncError(f"Không kết nối được tới Supabase: {e}") from e
        if r.status_code != 200:
            try:
                msg = r.json().get("error_description") or r.json().get("msg") or r.text
            except Exception:
                msg = r.text
            raise CloudSyncError(f"Đăng nhập thất bại (HTTP {r.status_code}): {msg}")
        d = r.json()
        self._access = d["access_token"]
        self._exp = datetime.now().timestamp() + int(d.get("expires_in", 3600)) - 60
        self.user_id = (d.get("user") or {}).get("id") or self.user_id
        self.refresh_token = d.get("refresh_token") or self.refresh_token
        if self.on_refresh_token and self.refresh_token:
            self.on_refresh_token(self.refresh_token)

    def sign_in(self):
        if self.refresh_token:
            try:
                return self._grant("refresh_token", {"refresh_token": self.refresh_token})
            except CloudSyncError:
                if not (self.email and self.password):
                    raise
        if not (self.email and self.password):
            raise CloudSyncError("Chưa đăng nhập: nhập email và mật khẩu Supabase (cùng tài khoản dùng trên web).")
        self._grant("password", {"email": self.email, "password": self.password})

    def token(self):
        if not self._access or datetime.now().timestamp() >= self._exp:
            self.sign_in()
        return self._access

    def refresh(self):
        self._access = None
        return self.token()


class StaticAuth:
    """Dùng cho test: token có sẵn."""

    def __init__(self, token, user_id):
        self._t, self.user_id = token, user_id

    def token(self):
        return self._t

    def refresh(self):
        return self._t


# ── Engine ───────────────────────────────────────────────────────────────────

class CloudSync:
    def __init__(self, supabase_url=None, anon_key=None, auth=None, progress_cb=None,
                 db_path=None, rest_url=None, timeout=30.0, deadline_s=None, wait_lock_s=0.0):
        self.rest = (rest_url or f"{(supabase_url or '').rstrip('/')}/rest/v1").rstrip("/")
        self.anon_key = anon_key or "anon"
        self.auth = auth
        self.progress_cb = progress_cb or (lambda m: None)
        self.timeout = timeout
        self._deadline = (time.monotonic() + deadline_s) if deadline_s else None   # tổng thời gian tối đa (dùng khi thoát app)
        self._db_path = db_path
        self._wait_lock_s = wait_lock_s
        self.db = None
        self.stats = {}

    # ── điểm vào ──
    def sync(self):
        """→ (ok, stats, error)"""
        self.stats = {"pushed": 0, "pulled": 0, "merged": 0, "conflicts": [], "deleted_local": 0,
                      "deleted_remote": 0, "errors": []}
        if not _SYNC_LOCK.acquire(blocking=False):
            return False, self.stats, "Đang có một lần đồng bộ khác chạy — hãy đợi nó xong rồi thử lại."
        # Khoá liên-tiến-trình: tiến trình sync ngầm (sau khi đóng app) và app mở lại không được chạy chồng lên nhau
        from infrastructure import sync_lock
        from database import db as _dbm
        self._file_lock = sync_lock.acquire((self._db_path or _dbm.DB_PATH) + ".sync.lock", self._wait_lock_s)
        if self._file_lock is None:
            _SYNC_LOCK.release()
            return False, self.stats, "Đang có một lần đồng bộ khác chạy — hãy đợi nó xong rồi thử lại."
        try:
            self._open()
            self._run()
            return True, self.stats, ""
        except AccountMismatch as e:
            self.stats["account_mismatch"] = True
            return False, self.stats, str(e)
        except CloudSyncError as e:
            return False, self.stats, str(e)
        except Exception as e:
            logger.exception("Cloud sync failed")
            try:
                import httpx
                if isinstance(e, httpx.RequestError):
                    return False, self.stats, f"Không kết nối được tới Supabase: {e}"
            except ImportError:
                return False, self.stats, "Thiếu thư viện httpx. Chạy: pip install httpx"
            return False, self.stats, str(e)
        finally:
            sync_lock.release(self._file_lock)
            _SYNC_LOCK.release()
            if self.db is not None:
                try:
                    self.db.close()
                except Exception:
                    pass
                self.db = None

    def _open(self):
        import httpx  # noqa: F401  (báo thiếu thư viện sớm)
        from database import db as dbmod
        path = self._db_path or dbmod.DB_PATH
        dbmod.init_db(db_path=path)                       # đảm bảo cột/trigger đồng bộ có đủ
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA busy_timeout = 30000")

    def _log(self, m):
        logger.info(m)
        self.progress_cb(m)

    # ── HTTP ──
    def _request(self, method, path, params=None, json_body=None, prefer=None, _retry=True):
        import httpx
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise CloudSyncError("Quá thời gian cho phép — sẽ đồng bộ tiếp ở lần sau.")
        headers = {"apikey": self.anon_key, "Authorization": f"Bearer {self.auth.token()}",
                   "Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        try:
            r = httpx.request(method, f"{self.rest}/{path}", params=params, json=json_body,
                              headers=headers, timeout=self.timeout)
        except httpx.RequestError as e:
            raise CloudSyncError(f"Không kết nối được tới Supabase: {e}") from e
        if r.status_code == 401 and _retry:
            self.auth.refresh()
            return self._request(method, path, params, json_body, prefer, _retry=False)
        return r

    @staticmethod
    def _err(r):
        try:
            d = r.json()
            msg = d.get("message") or str(d)
            if d.get("code") == "42501" or "row-level security" in msg:   # RLS: tài khoản bị khóa / không đủ quyền
                msg = "Tài khoản đang bị khóa hoặc không đủ quyền ghi (liên hệ quản trị viên). Dữ liệu trên máy vẫn được giữ và sẽ gửi lại khi được mở khóa."
            return d.get("code", ""), msg
        except Exception:
            return "", r.text or f"HTTP {r.status_code}"

    def _ok(self, r, what):
        if r.status_code >= 400:
            code, msg = self._err(r)
            if r.status_code == 401:
                raise CloudSyncError("Phiên đăng nhập không hợp lệ — hãy đăng nhập lại trong hộp thoại Sync.")
            raise CloudSyncError(f"{what}: {msg} (HTTP {r.status_code}{', ' + code if code else ''})")
        return r

    def _get_all(self, table, params):
        out, offset = [], 0
        while True:
            p = dict(params, limit=PAGE, offset=offset)
            rows = self._ok(self._request("GET", table, p), f"Tải {table}").json()
            out.extend(rows)
            if not rows:                       # đọc tới khi trang rỗng (máy chủ có thể giới hạn max-rows nhỏ hơn PAGE)
                return out
            offset += len(rows)

    def _get_one(self, table, row_id):
        rows = self._ok(self._request("GET", table, {"select": "*", "id": f"eq.{row_id}"}), f"Tải {table}").json()
        return rows[0] if rows else None

    def _sig(self):
        r = self._request("POST", "rpc/jp_sync_sig", json_body={})
        return r.json() if r.status_code == 200 else None

    # ── trạng thái / giao dịch cục bộ ──
    def _state(self, key, default=None):
        r = self.db.execute("SELECT value FROM _sync_state WHERE key=?", (key,)).fetchone()
        return r[0] if r else default

    def _set_state(self, key, value):
        self.db.execute("INSERT INTO _sync_state (key,value) VALUES (?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    @contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute("UPDATE _sync_ctx SET active=1")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("UPDATE _sync_ctx SET active=0")
            self.db.execute("COMMIT")

    def _local(self, table, row_id):
        return self.db.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()

    # ── chuyển đổi hàng ──
    def _snap(self, table, row):
        """Hàng cục bộ → dạng máy chủ (chỉ các trường sửa được)."""
        o = {}
        for f in FIELDS[table]:
            v = row[f]
            if f in ("is_favorite", "hidden"):
                v = bool(v)
            elif f == "deleted_at":
                v = local_to_utc(v)
            elif f in ("stroke_count", "sort_order", "grp"):
                v = None if v in (None, "") else int(v)
            elif f == "status":
                v = v if v in CARD_STATUSES else "new"
            elif f == "pos":
                v = v if v in CARD_POS else None          # máy chủ có CHECK: giá trị lạ → NULL thay vì bị từ chối
            else:
                v = _norm(v)
            o[f] = v
        return o

    @staticmethod
    def _from_remote(table, r):
        """Hàng máy chủ → các cột cục bộ."""
        o = {}
        for f in FIELDS[table]:
            v = r.get(f)
            if f in ("is_favorite", "hidden"):
                v = 1 if v else 0
            elif f == "deleted_at":
                v = utc_to_local(v)
            o[f] = v
        if table == "cards":
            for f in SRS_FIELDS:
                if f in r:
                    o[f] = r.get(f)
        o["created_at"] = utc_to_local(r.get("created_at"))
        o["updated_at"] = utc_to_local(r.get("updated_at"))
        return o

    @staticmethod
    def _base_of(table, r):
        b = {f: r.get(f) for f in FIELDS[table]}
        b["version"] = r.get("version")
        b["updated_at"] = r.get("updated_at")
        return b

    def _set_row(self, table, row_id, cols):
        sets = ", ".join(f"{k}=?" for k in cols)
        self.db.execute(f"UPDATE {table} SET {sets} WHERE id=?", list(cols.values()) + [row_id])

    # ════════════════════════════════════════════════════════════════════════
    def _run(self):
        self._log("🔐 Đăng nhập Supabase...")
        self.auth.token()
        v = self._request("POST", "rpc/jp_schema_version", json_body={})
        if v.status_code != 200 or not (isinstance(v.json(), int) and v.json() >= SCHEMA_MIN):
            raise CloudSyncError("Cơ sở dữ liệu Supabase chưa được nâng cấp: hãy chạy lại TOÀN BỘ file schema.sql "
                                 "(bản web v3) trong Supabase → SQL Editor, rồi đồng bộ lại.")
        self._check_account()
        sig0 = self._sig()
        if not self._has_local_changes() and sig0 is not None and sig0 == self._state("sig"):
            self._log("✅ Không có gì thay đổi.")
            return

        self._log("🗑️  Gửi các mục đã xóa vĩnh viễn...")
        self._push_tombstones()
        self._log("⬆️  Gửi mục mới (danh mục, bộ thẻ, bộ thủ, thẻ)...")
        self._push_categories()
        for t in VERSIONED:
            self._push_versioned(t, only_new=True)
        self._log("📚 Gửi lượt ôn tập...")
        self._push_sessions()
        self._log("⬇️  Kéo thay đổi từ máy chủ...")
        self._pull_categories()
        for t in VERSIONED:
            self._pull_versioned(t)
        self._reconcile_hard_deletes(sig0)
        self._log("🔀 Gửi các chỉnh sửa (gộp theo trường nếu có xung đột)...")
        for t in VERSIONED:
            self._push_versioned(t, only_new=False)
        self._push_categories()          # đổi tên/biểu tượng danh mục
        self._sync_links("deck_cards", "deck_id", "decks")
        self._sync_links("radical_cards", "radical_id", "radicals")
        self._sync_decomps()
        self._sync_cells()
        self._pull_sessions()
        # Chỉ lưu chữ ký đọc TRƯỚC khi kéo, và chỉ khi lần này không đẩy gì: thay đổi của máy khác xen giữa
        # lúc kéo và lúc kết thúc sẽ không bị "nuốt" vào chữ ký đã lưu.
        s0 = self.stats
        wrote = s0["pushed"] or s0["merged"] or s0["deleted_remote"] or s0["deleted_local"] or s0["errors"]
        self._set_state("sig", "" if (wrote or sig0 is None) else sig0)
        s = self.stats
        self._log(f"✅ Xong | đẩy {s['pushed']} · kéo {s['pulled']} · gộp {s['merged']} · xung đột {len(s['conflicts'])}")
        for c in s["conflicts"]:
            self._log("   ⚠️ " + c)

    def _check_account(self):
        """Database cục bộ chỉ được đồng bộ với đúng 1 tài khoản + máy chủ (lưu ở lần đồng bộ đầu).
        Đổi tài khoản trên cùng DB sẽ xoá dữ liệu tài khoản cũ khỏi máy và đẩy dữ liệu chưa gửi sang tài khoản mới → chặn."""
        uid = getattr(self.auth, "user_id", None)
        if not uid:
            return
        bound, bound_rest = self._state("user_id"), self._state("rest")
        if bound and (bound != uid or (bound_rest and bound_rest != self.rest)):
            raise AccountMismatch(
                "Database trên máy này đang liên kết với một tài khoản/máy chủ Supabase khác. "
                "Để dùng tài khoản này, hãy đặt lại liên kết đồng bộ (dữ liệu trên máy được giữ nguyên và sẽ được gửi lên tài khoản mới).")
        if not bound:
            self._set_state("user_id", uid)
        if not bound_rest:
            self._set_state("rest", self.rest)

    def _has_local_changes(self):
        for t in ("cards", "decks", "radicals", "deck_categories", "deck_cards", "radical_cards", "user_decompositions",
                  "grammar_points", "translations", "conj_forms", "conj_verbs", "conj_cells"):
            if self.db.execute(f"SELECT 1 FROM {t} WHERE dirty=1 LIMIT 1").fetchone():
                return True
        return bool(self.db.execute("SELECT 1 FROM study_sessions WHERE dirty IN (1,2) LIMIT 1").fetchone()
                    or self.db.execute("SELECT 1 FROM _sync_tombstones LIMIT 1").fetchone())

    # ── xóa vĩnh viễn ───────────────────────────────────────────────────────
    def _push_tombstones(self):
        rows = self.db.execute("SELECT tbl,row_id FROM _sync_tombstones").fetchall()
        for t, rid in rows:
            if t == "conj_cells":
                vid, _, fid = rid.partition("|")
                r = self._request("DELETE", t, {"verb_id": f"eq.{vid}", "form_id": f"eq.{fid}"})
            else:
                r = self._request("DELETE", t, {"id": f"eq.{rid}"})
            if r.status_code in (200, 204):
                self.stats["deleted_remote"] += 1
                self.db.execute("DELETE FROM _sync_tombstones WHERE tbl=? AND row_id=?", (t, rid))
            else:
                self.stats["errors"].append(f"Không xóa được {t}/{rid[:8]}: {self._err(r)[1]}")

    def _reconcile_hard_deletes(self, sig0):
        """Mục đã bị xóa vĩnh viễn ở máy khác → xóa khỏi máy này (nếu bạn chưa sửa dở; nếu đã sửa dở thì tạo lại)."""
        if sig0 is not None and sig0 == self._state("sig") and not self._has_local_changes():
            return
        self._reconcile_cells()
        for t in HARD_DELETE_TABLES:
            remote_ids = {r["id"] for r in self._get_all(t, {"select": "id", "order": "id"})}
            for row in self.db.execute(f"SELECT id, dirty FROM {t} WHERE base_json IS NOT NULL").fetchall():
                if row["id"] in remote_ids:
                    continue
                try:
                    with self._tx():
                        if row["dirty"]:
                            self._set_row(t, row["id"], {"base_json": None, "server_version": None, "dirty": 1})
                        else:
                            if t == "deck_categories":                   # bộ thẻ đang tham chiếu danh mục này → bỏ tham chiếu (máy chủ cũng đã đặt NULL)
                                self.db.execute("UPDATE decks SET category_id=NULL WHERE category_id=?", (row["id"],))
                            self.db.execute(f"DELETE FROM {t} WHERE id=?", (row["id"],))
                            self.stats["deleted_local"] += 1
                except sqlite3.IntegrityError as e:
                    self.stats["errors"].append(f"Không xoá được {t}/{row['id'][:8]} trên máy: {e}")

    # ── danh mục (không có version/updated_at: người ghi sau thắng) ─────────
    def _push_categories(self):
        for row in self.db.execute("SELECT * FROM deck_categories WHERE dirty=1").fetchall():
            payload = {"name": row["name"], "icon": row["icon"], "sort_order": row["sort_order"] or 0}
            try:
                if row["base_json"] is None:
                    r = self._request("POST", "deck_categories", json_body=dict(payload, id=row["id"], created_at=local_to_utc(row["created_at"])),
                                      prefer="return=representation")
                    if r.status_code == 409:
                        ex = self._get_one("deck_categories", row["id"])
                        if ex is None:                                   # trùng tên với danh mục khác → dùng danh mục đó
                            found = self._ok(self._request("GET", "deck_categories", {"select": "*", "name": f"eq.{row['name']}"}), "Tải danh mục").json()
                            if found:
                                with self._tx():
                                    self._reid("deck_categories", row["id"], found[0]["id"])
                                continue
                        r = self._request("PATCH", "deck_categories", {"id": f"eq.{row['id']}"}, payload, "return=representation")
                else:
                    r = self._request("PATCH", "deck_categories", {"id": f"eq.{row['id']}"}, payload, "return=representation")
                self._ok(r, "Gửi danh mục")
                self._finish_simple("deck_categories", row, "id")
                self.stats["pushed"] += 1
            except CloudSyncError as e:
                self.stats["errors"].append(str(e))

    def _pull_categories(self):
        remote = self._get_all("deck_categories", {"select": "*", "order": "id"})
        for r in remote:
            with self._tx():
                loc = self._local("deck_categories", r["id"])
                if loc is not None and loc["dirty"]:
                    continue
                vals = {"name": r["name"], "icon": r.get("icon"), "sort_order": r.get("sort_order") or 0,
                        "base_json": "{}", "dirty": 0}
                if loc is None:
                    # trùng tên với 1 danh mục cục bộ chưa đồng bộ → gộp về id máy chủ
                    twin = self.db.execute("SELECT id FROM deck_categories WHERE name=?", (r["name"],)).fetchone()
                    if twin is not None:
                        self._reid("deck_categories", twin["id"], r["id"])
                        self._set_row("deck_categories", r["id"], vals)
                    else:
                        self.db.execute("INSERT INTO deck_categories (id,name,icon,sort_order,created_at,base_json,dirty) VALUES (?,?,?,?,?,?,0)",
                                        (r["id"], r["name"], r.get("icon"), r.get("sort_order") or 0, utc_to_local(r.get("created_at")), "{}"))
                        self.stats["pulled"] += 1
                elif (loc["name"], loc["icon"], loc["sort_order"]) != (vals["name"], vals["icon"], vals["sort_order"]):
                    self._set_row("deck_categories", r["id"], vals)
                    self.stats["pulled"] += 1
                else:
                    self._set_row("deck_categories", r["id"], {"base_json": "{}", "dirty": 0})

    def _finish_simple(self, table, snapshot_row, key):
        """Đánh dấu sạch nếu hàng chưa bị sửa tiếp trong lúc gửi."""
        with self._tx():
            cur = self.db.execute(f"SELECT * FROM {table} WHERE {key}=?", (snapshot_row[key],)).fetchone()
            if cur is None:
                return
            unchanged = all(cur[k] == snapshot_row[k] for k in snapshot_row.keys() if k not in ("dirty", "base_json", "server_version", "updated_at"))
            self.db.execute(f"UPDATE {table} SET base_json=?, dirty=? WHERE {key}=?", ("{}", 0 if unchanged else 1, snapshot_row[key]))

    # ── đổi id (gộp trùng) ──────────────────────────────────────────────────
    def _reid(self, table, old, new):
        """Đổi khoá chính cục bộ `old` → `new` kèm các bảng con (phải gọi trong _tx)."""
        if old == new:
            return
        self.db.execute("PRAGMA defer_foreign_keys = ON")
        if self.db.execute(f"SELECT 1 FROM {table} WHERE id=?", (new,)).fetchone():
            # id đích đã có cục bộ: chuyển con sang đích rồi bỏ hàng cũ
            for child, col in CHILDREN.get(table, []):
                self.db.execute(f"UPDATE OR IGNORE {child} SET {col}=? WHERE {col}=?", (new, old))
                self.db.execute(f"DELETE FROM {child} WHERE {col}=?", (old,))
            self.db.execute(f"DELETE FROM {table} WHERE id=?", (old,))
            return
        for child, col in CHILDREN.get(table, []):
            self.db.execute(f"UPDATE OR IGNORE {child} SET {col}=? WHERE {col}=?", (new, old))
            self.db.execute(f"DELETE FROM {child} WHERE {col}=?", (old,))
        self.db.execute(f"UPDATE {table} SET id=? WHERE id=?", (new, old))

    # ── cards / decks / radicals ────────────────────────────────────────────
    def _pull_versioned(self, table):
        cur = self._state(f"cursor:{table}")
        params = {"select": "*", "order": "updated_at.asc,id.asc"}
        if cur:
            params["updated_at"] = "gte." + (_aware(cur) - CURSOR_OVERLAP).astimezone(timezone.utc).isoformat()
        rows = self._get_all(table, params)
        for r in rows:
            self._pull_apply(table, r)
        if rows:
            self._set_state(f"cursor:{table}", max(r["updated_at"] for r in rows))

    def _pending_sessions(self, card_id):
        return self.db.execute("SELECT 1 FROM study_sessions WHERE card_id=? AND dirty=1 LIMIT 1", (card_id,)).fetchone() is not None

    def _pull_apply(self, table, r):
        with self._tx():
            loc = self._local(table, r["id"])
            if loc is not None and loc["server_version"] == r["version"] and loc["base_json"]:
                return                                                    # đã khớp (chính lần đẩy của mình)
            if loc is None:
                if self.db.execute("SELECT 1 FROM _sync_tombstones WHERE tbl=? AND row_id=?", (table, r["id"])).fetchone():
                    return                                                # bạn đã xoá vĩnh viễn mục này, lần xoá trên máy chủ chưa thành công → đừng tạo lại
                key = UNIQUE_KEY.get(table)
                twin = None
                if key and not r.get("deleted_at"):
                    twin = self.db.execute(f"SELECT * FROM {table} WHERE {key}=? AND deleted_at IS NULL AND base_json IS NULL", (r[key],)).fetchone()
                if twin is not None:                                      # hàng cục bộ mới tạo trùng khoá với hàng này
                    self._reid(table, twin["id"], r["id"])
                    loc = self._local(table, r["id"])
                else:
                    self._insert_local(table, r)
                    self.stats["pulled"] += 1
                    return
            base = json.loads(loc["base_json"]) if loc["base_json"] else None
            if base is not None and not diff_fields(base, self._snap(table, loc), FIELDS[table]):
                self._overwrite_local(table, loc, r)                     # chưa sửa gì cục bộ → nhận bản máy chủ
                self.stats["pulled"] += 1
            # còn lại: đang sửa dở → xử lý ở bước đẩy (gộp 3 chiều)

    def _insert_local(self, table, r):
        cols = self._from_remote(table, r)
        cols.update(id=r["id"], server_version=r["version"], base_json=json.dumps(self._base_of(table, r)), dirty=0)
        names = ", ".join(cols)
        try:
            self.db.execute(f"INSERT INTO {table} ({names}) VALUES ({','.join('?' * len(cols))})", list(cols.values()))
        except sqlite3.IntegrityError:
            key = UNIQUE_KEY.get(table)
            if key and cols.get(key):                                     # trùng khoá với 1 hàng đã đồng bộ khác: đổi tên, đẩy lại sau
                cols[key] = f"{cols[key]} ({r['id'][:4]})"
                cols["dirty"] = 1
                self.db.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({','.join('?' * len(cols))})", list(cols.values()))
                self.stats["conflicts"].append(f"{table}: trùng tên '{r[key]}' — đã đổi tên bản cục bộ thành '{cols[key]}'")
            else:
                raise

    def _overwrite_local(self, table, loc, r):
        cols = self._from_remote(table, r)
        if table == "cards" and self._pending_sessions(loc["id"]):
            for f in SRS_FIELDS + ["status"]:
                cols.pop(f, None)
        cols.update(server_version=r["version"], base_json=json.dumps(self._base_of(table, r)), dirty=0)
        try:
            self._set_row(table, loc["id"], cols)
        except sqlite3.IntegrityError:
            key = UNIQUE_KEY.get(table)
            if not key:
                raise
            cols[key] = f"{cols[key]} ({r['id'][:4]})"
            cols["dirty"] = 1
            self._set_row(table, loc["id"], cols)

    def _push_versioned(self, table, only_new):
        q = f"SELECT * FROM {table} WHERE dirty=1" + (" AND base_json IS NULL" if only_new else "")
        for row in self.db.execute(q).fetchall():
            try:
                self._push_row(table, row)
            except CloudSyncError as e:
                self.stats["errors"].append(f"{table}/{row['id'][:8]}: {e}")

    @staticmethod
    def _server_fix(table, d):
        """Cột NOT NULL trên máy chủ: chuỗi rỗng cục bộ (đã chuẩn hóa thành None khi so sánh) phải gửi là ''."""
        if table == "grammar_points" and "meaning_vi" in d and d["meaning_vi"] is None:
            d = dict(d, meaning_vi="")
        return d

    def _insert_payload(self, table, row, snap):
        p = {"id": row["id"], **self._server_fix(table, snap), "created_at": local_to_utc(row["created_at"])}
        if table == "cards":
            p.update(srs_interval=row["srs_interval"] or 1, srs_ease=row["srs_ease"] or 2.5,
                     srs_due_date=(row["srs_due_date"] or None), study_count=row["study_count"] or 0)
        return p

    def _push_row(self, table, row):
        snap = self._snap(table, row)
        fields = FIELDS[table]
        if table == "cards" and (snap["type"] not in CARD_TYPES or not snap["character"] or not snap["meaning_vi"]):
            raise CloudSyncError("thẻ thiếu loại/chữ/nghĩa hợp lệ — bỏ qua")
        base = json.loads(row["base_json"]) if row["base_json"] else None
        if base is None:
            remote = self._insert_row(table, row, snap)
            if remote is None:
                return
        else:
            ch = diff_fields(base, snap, fields)
            if not ch:
                with self._tx():                                          # chỉ đổi trường cục bộ/SRS → không cần gửi
                    cur = self._local(table, row["id"])
                    if cur is not None and not diff_fields(base, self._snap(table, cur), fields):
                        self.db.execute(f"UPDATE {table} SET dirty=0 WHERE id=?", (row["id"],))
                return
            remote = self._patch_row(table, row, snap, base, ch)
            if remote is None:
                return
        self._commit_row(table, row["id"], snap, remote)
        self.stats["pushed"] += 1

    def _insert_row(self, table, row, snap):
        r = self._request("POST", table, json_body=self._insert_payload(table, row, snap), prefer="return=representation")
        if r.status_code == 201:
            return r.json()[0]
        code, msg = self._err(r)
        if r.status_code == 409 and code == "23505":
            ex = self._get_one(table, row["id"])
            if ex is None and table in UNIQUE_KEY and not snap.get("deleted_at"):
                key = UNIQUE_KEY[table]
                f = self._ok(self._request("GET", table, {"select": "*", key: f"eq.{snap[key]}", "deleted_at": "is.null"}), "Tải").json()
                if f:                                                      # trùng tên/ký tự → dùng hàng đã có trên máy chủ
                    with self._tx():
                        self._reid(table, row["id"], f[0]["id"])
                    ex = f[0]
                    row = self._local(table, ex["id"]) or row
            if ex is not None:
                # đã có trên máy chủ (gửi lại sau khi mất phản hồi, hoặc trùng): coi như lần đầu gặp nhau
                base = self._base_of(table, ex)
                ch = diff_fields(base, snap, FIELDS[table])
                if not ch:
                    return ex
                return self._patch_row(table, row, snap, base, ch, first_contact=True)
        raise CloudSyncError(f"gửi {table}: {msg}")

    def _patch_row(self, table, row, snap, base, ch, first_contact=False):
        for _ in range(5):
            r = self._request("PATCH", table, {"id": f"eq.{row['id']}", "version": f"eq.{base['version']}"}, self._server_fix(table, ch), "return=representation")
            if r.status_code == 409 and table in UNIQUE_KEY and self._err(r)[0] == "23505":
                key = UNIQUE_KEY[table]
                if key in ch:                                              # đổi tên trùng với bộ khác → thêm hậu tố
                    ch[key] = f"{ch[key]} ({row['id'][:4]})"
                    self.stats["conflicts"].append(f"{table}: tên '{snap[key]}' đã tồn tại — đổi thành '{ch[key]}'")
                    continue
            self._ok(r, f"Cập nhật {table}")
            rows = r.json()
            if rows:
                return rows[0]
            remote = self._get_one(table, row["id"])
            if remote is None:                                             # đã bị xóa vĩnh viễn ở nơi khác → tạo lại
                return self._insert_row(table, row, snap)
            apply, conflicts = plan_merge(base, ch, remote)
            apply = dict(apply)
            local_ts = _aware(row["updated_at"])
            remote_ts = _aware(remote.get("updated_at"))
            for f, b, mine, theirs in conflicts:
                keep_mine = bool(first_contact and False) or (local_ts is not None and remote_ts is not None and local_ts > remote_ts)
                label = f"{table}: '{snap.get('character') or snap.get('name') or row['id'][:8]}' · {f}"
                self._record_conflict(table, row["id"], label, f, mine, theirs, "máy này" if keep_mine else "máy chủ")
                if keep_mine:
                    apply[f] = mine
            self.stats["merged"] += 1
            base = self._base_of(table, remote)
            ch = apply
            if not ch:
                return remote
        raise CloudSyncError("mục đang được sửa liên tục từ thiết bị khác, thử lại sau")

    def _record_conflict(self, table, rid, label, field, mine, theirs, kept):
        self.stats["conflicts"].append(f"{label}: máy này = {mine!r} · máy chủ = {theirs!r} → giữ bản {kept}")
        self.db.execute("INSERT INTO sync_conflicts (tbl,row_id,label,field,local_value,remote_value,kept) VALUES (?,?,?,?,?,?,?)",
                        (table, rid, label, field, None if mine is None else str(mine), None if theirs is None else str(theirs), kept))

    def _commit_row(self, table, row_id, snapshot, remote):
        """Ghi kết quả máy chủ về hàng cục bộ, KHÔNG đè lên những gì bạn vừa sửa trong lúc đang gửi."""
        with self._tx():
            cur = self._local(table, row_id)
            if cur is None:
                return
            cols = self._from_remote(table, remote)
            curR = self._snap(table, cur)
            keep = [f for f in FIELDS[table] if not same(f, curR[f], snapshot[f])]   # trường bạn đã sửa tiếp
            for f in keep:
                cols.pop(f, None)
            if table == "cards" and self._pending_sessions(row_id):
                for f in SRS_FIELDS + ["status"]:
                    cols.pop(f, None)
            base = self._base_of(table, remote)
            cols.update(server_version=remote["version"], base_json=json.dumps(base))
            self._set_row(table, row_id, cols)
            nxt = self._local(table, row_id)
            self.db.execute(f"UPDATE {table} SET dirty=? WHERE id=?",
                            (1 if diff_fields(base, self._snap(table, nxt), FIELDS[table]) else 0, row_id))

    # ── lượt ôn tập ────────────────────────────────────────────────────────
    def _push_sessions(self):
        hist = self.db.execute("SELECT * FROM study_sessions WHERE dirty=2 ORDER BY studied_at").fetchall()
        for i in range(0, len(hist), 200):
            batch = hist[i:i + 200]
            body = [{"id": s["id"], "card_id": s["card_id"], "result": s["result"], "studied_at": local_to_utc(s["studied_at"])} for s in batch]
            r = self._request("POST", "study_sessions", {"on_conflict": "id"}, body, "resolution=ignore-duplicates,return=minimal")
            if r.status_code >= 400:
                for s, b in zip(batch, body):                              # có dòng lỗi (vd thẻ chưa lên được) → thử từng dòng
                    rr = self._request("POST", "study_sessions", {"on_conflict": "id"}, [b], "resolution=ignore-duplicates,return=minimal")
                    if rr.status_code < 400:
                        self.db.execute("UPDATE study_sessions SET dirty=0 WHERE id=?", (s["id"],))
                    else:
                        self.stats["errors"].append(f"lượt ôn {s['id'][:8]}: {self._err(rr)[1]}")
                continue
            with self._tx():
                self.db.executemany("UPDATE study_sessions SET dirty=0 WHERE id=?", [(s["id"],) for s in batch])
            self.stats["pushed"] += len(batch)
        new = self.db.execute("SELECT * FROM study_sessions WHERE dirty=1 ORDER BY studied_at, rowid").fetchall()
        for s in new:
            r = self._request("POST", "rpc/log_study", json_body={
                "p_id": s["id"], "p_card": s["card_id"], "p_result": s["result"],
                "p_at": local_to_utc(s["studied_at"]), "p_today": str(s["studied_at"])[:10]})
            if r.status_code >= 400:
                code, msg = self._err(r)
                if r.status_code >= 500 or r.status_code == 401:
                    raise CloudSyncError(f"log_study: {msg}")
                self.stats["errors"].append(f"lượt ôn {s['id'][:8]} bị từ chối: {msg}")
                continue
            card = r.json()
            with self._tx():
                self.db.execute("UPDATE study_sessions SET dirty=0 WHERE id=?", (s["id"],))
                if isinstance(card, dict) and card.get("id"):
                    self._adopt_study_card(card)
            self.stats["pushed"] += 1

    def _adopt_study_card(self, card):
        """Máy chủ là bên tính SRS: nhận lại interval/ease/due/status, cập nhật mốc để lần sau không coi là sửa tay."""
        loc = self._local("cards", card["id"])
        if loc is None or not loc["base_json"] or self._pending_sessions(card["id"]):
            return
        base = json.loads(loc["base_json"])
        base["version"] = card["version"]
        self._set_row("cards", card["id"], {
            "srs_interval": card["srs_interval"], "srs_ease": card["srs_ease"], "srs_due_date": card["srs_due_date"],
            "status": card["status"], "study_count": card.get("study_count", 0) or 0, "server_version": card["version"], "base_json": json.dumps(base)})
        cur = self._local("cards", card["id"])
        self.db.execute("UPDATE cards SET dirty=? WHERE id=?", (1 if diff_fields(base, self._snap("cards", cur), CARD_FIELDS) else 0, card["id"]))

    def _pull_sessions(self):
        cur = self._state("cursor:study_sessions")
        params = {"select": "id,card_id,result,studied_at", "order": "studied_at.asc,id.asc"}
        if cur:
            params["studied_at"] = "gte." + (_aware(cur) - SESSION_OVERLAP).astimezone(timezone.utc).isoformat()
        rows = self._get_all("study_sessions", params)
        with self._tx():
            known = {r[0] for r in self.db.execute("SELECT id FROM cards")}
            for r in rows:
                if r["card_id"] not in known:
                    continue
                c = self.db.execute("INSERT OR IGNORE INTO study_sessions (id,card_id,result,studied_at,dirty) VALUES (?,?,?,?,0)",
                                    (r["id"], r["card_id"], r["result"], utc_to_local(r["studied_at"])))
                self.stats["pulled"] += c.rowcount
        if rows:
            self._set_state("cursor:study_sessions", max(r["studied_at"] for r in rows))

    # ── liên kết thẻ ↔ bộ / bộ thủ (người ghi sau thắng) ────────────────────
    def _sync_links(self, table, parent_col, parent_table):
        # đẩy
        for row in self.db.execute(f"SELECT * FROM {table} WHERE dirty=1").fetchall():
            if not self._exists_remote(parent_table, row[parent_col]) or not self._exists_remote("cards", row["card_id"]):
                continue
            body = {parent_col: row[parent_col], "card_id": row["card_id"],
                    "added_at": local_to_utc(row["added_at"]), "deleted_at": local_to_utc(row["deleted_at"])}
            r = self._request("POST", table, {"on_conflict": f"{parent_col},card_id"}, body, "resolution=merge-duplicates,return=representation")
            if r.status_code >= 400:
                self.stats["errors"].append(f"{table}: {self._err(r)[1]}")
                continue
            srv = r.json()[0]
            with self._tx():
                cur = self.db.execute(f"SELECT * FROM {table} WHERE {parent_col}=? AND card_id=?", (row[parent_col], row["card_id"])).fetchone()
                if cur is None:
                    continue
                unchanged = (cur["deleted_at"] is None) == (row["deleted_at"] is None)
                self.db.execute(f"UPDATE {table} SET id=?, base_json='{{}}', dirty=? WHERE {parent_col}=? AND card_id=?",
                                (srv["id"], 0 if unchanged else 1, row[parent_col], row["card_id"]))
            self.stats["pushed"] += 1
        # kéo
        key = f"cursor:{table}"
        cur = self._state(key)
        params = {"select": "*", "order": "updated_at.asc,id.asc"}
        if cur:
            params["updated_at"] = "gte." + (_aware(cur) - CURSOR_OVERLAP).astimezone(timezone.utc).isoformat()
        rows = self._get_all(table, params)
        with self._tx():
            for r in rows:
                if not self.db.execute(f"SELECT 1 FROM {parent_table} WHERE id=?", (r[parent_col],)).fetchone() \
                        or not self.db.execute("SELECT 1 FROM cards WHERE id=?", (r["card_id"],)).fetchone():
                    continue
                loc = self.db.execute(f"SELECT * FROM {table} WHERE {parent_col}=? AND card_id=?", (r[parent_col], r["card_id"])).fetchone()
                dele = utc_to_local(r.get("deleted_at"))
                if loc is None:
                    self.db.execute(f"INSERT OR IGNORE INTO {table} (id,{parent_col},card_id,added_at,updated_at,deleted_at,base_json,dirty) VALUES (?,?,?,?,?,?,'{{}}',0)",
                                    (r["id"], r[parent_col], r["card_id"], utc_to_local(r.get("added_at")), utc_to_local(r.get("updated_at")), dele))
                    self.stats["pulled"] += 1
                elif not loc["dirty"] and ((loc["deleted_at"] is None) != (dele is None) or loc["id"] != r["id"]):
                    self.db.execute(f"UPDATE {table} SET id=?, deleted_at=?, updated_at=?, base_json='{{}}', dirty=0 WHERE {parent_col}=? AND card_id=?",
                                    (r["id"], dele, utc_to_local(r.get("updated_at")), r[parent_col], r["card_id"]))
                    self.stats["pulled"] += 1
        if rows:
            self._set_state(key, max(r["updated_at"] for r in rows))

    def _exists_remote(self, table, row_id):
        # cha đã đẩy ở bước trước (base_json có giá trị) → chắc chắn có trên máy chủ
        r = self.db.execute(f"SELECT base_json FROM {table} WHERE id=?", (row_id,)).fetchone()
        return r is not None and r[0] is not None

    # ── ô của bảng chia động từ (khoá kép verb_id + form_id; không version: người ghi sau thắng) ──
    def _sync_cells(self):
        for row in self.db.execute("SELECT * FROM conj_cells WHERE dirty=1").fetchall():
            if not self._exists_remote("conj_verbs", row["verb_id"]) or not self._exists_remote("conj_forms", row["form_id"]):
                continue
            body = {"verb_id": row["verb_id"], "form_id": row["form_id"], "value": row["value"]}
            r = self._request("POST", "conj_cells", {"on_conflict": "verb_id,form_id"}, body, "resolution=merge-duplicates,return=minimal")
            if r.status_code >= 400:
                self.stats["errors"].append(f"conj_cells: {self._err(r)[1]}")
                continue
            with self._tx():
                cur = self.db.execute("SELECT value FROM conj_cells WHERE verb_id=? AND form_id=?", (row["verb_id"], row["form_id"])).fetchone()
                self.db.execute("UPDATE conj_cells SET base_json='{}', dirty=? WHERE verb_id=? AND form_id=?",
                                (0 if cur is not None and cur[0] == row["value"] else 1, row["verb_id"], row["form_id"]))
            self.stats["pushed"] += 1
        key = "cursor:conj_cells"
        cur = self._state(key)
        params = {"select": "*", "order": "updated_at.asc,verb_id.asc,form_id.asc"}
        if cur:
            params["updated_at"] = "gte." + (_aware(cur) - CURSOR_OVERLAP).astimezone(timezone.utc).isoformat()
        rows = self._get_all("conj_cells", params)
        with self._tx():
            for r in rows:
                if not self.db.execute("SELECT 1 FROM conj_verbs WHERE id=?", (r["verb_id"],)).fetchone() \
                        or not self.db.execute("SELECT 1 FROM conj_forms WHERE id=?", (r["form_id"],)).fetchone():
                    continue
                loc = self.db.execute("SELECT * FROM conj_cells WHERE verb_id=? AND form_id=?", (r["verb_id"], r["form_id"])).fetchone()
                if loc is None:
                    self.db.execute("INSERT INTO conj_cells (verb_id,form_id,value,updated_at,base_json,dirty) VALUES (?,?,?,?,'{}',0)",
                                    (r["verb_id"], r["form_id"], r["value"], utc_to_local(r.get("updated_at"))))
                    self.stats["pulled"] += 1
                elif not loc["dirty"] and loc["value"] != r["value"]:
                    self.db.execute("UPDATE conj_cells SET value=?, updated_at=?, base_json='{}', dirty=0 WHERE verb_id=? AND form_id=?",
                                    (r["value"], utc_to_local(r.get("updated_at")), r["verb_id"], r["form_id"]))
                    self.stats["pulled"] += 1
        if rows:
            self._set_state(key, max(r["updated_at"] for r in rows))

    def _reconcile_cells(self):
        """Ô đã bị xóa ở máy khác → xóa khỏi máy này (nếu bạn chưa sửa dở)."""
        remote = {(r["verb_id"], r["form_id"]) for r in self._get_all("conj_cells", {"select": "verb_id,form_id", "order": "verb_id,form_id"})}
        for row in self.db.execute("SELECT verb_id, form_id, dirty FROM conj_cells WHERE base_json IS NOT NULL").fetchall():
            if (row["verb_id"], row["form_id"]) in remote or row["dirty"]:
                continue
            with self._tx():
                self.db.execute("DELETE FROM conj_cells WHERE verb_id=? AND form_id=?", (row["verb_id"], row["form_id"]))
            self.stats["deleted_local"] += 1

    # ── tách bộ do người dùng định nghĩa (người ghi sau thắng) ──────────────
    def _sync_decomps(self):
        uid = self.auth.user_id
        for row in self.db.execute("SELECT * FROM user_decompositions WHERE dirty=1").fetchall():
            body = {"user_id": uid, "character": row["character"], "parts": row["parts"], "deleted_at": local_to_utc(row["deleted_at"])}
            r = self._request("POST", "user_decompositions", {"on_conflict": "user_id,character"}, body, "resolution=merge-duplicates,return=minimal")
            if r.status_code >= 400:
                self.stats["errors"].append(f"user_decompositions: {self._err(r)[1]}")
                continue
            with self._tx():
                cur = self.db.execute("SELECT * FROM user_decompositions WHERE character=?", (row["character"],)).fetchone()
                same_ = cur is not None and cur["parts"] == row["parts"] and (cur["deleted_at"] is None) == (row["deleted_at"] is None)
                self.db.execute("UPDATE user_decompositions SET base_json='{}', dirty=? WHERE character=?", (0 if same_ else 1, row["character"]))
            self.stats["pushed"] += 1
        key = "cursor:user_decompositions"
        cur = self._state(key)
        params = {"select": "*", "order": "updated_at.asc,character.asc"}
        if cur:
            params["updated_at"] = "gte." + (_aware(cur) - CURSOR_OVERLAP).astimezone(timezone.utc).isoformat()
        rows = self._get_all("user_decompositions", params)
        with self._tx():
            for r in rows:
                loc = self.db.execute("SELECT * FROM user_decompositions WHERE character=?", (r["character"],)).fetchone()
                if loc is not None and loc["dirty"]:
                    continue
                dele = utc_to_local(r.get("deleted_at"))
                if loc is None:
                    self.db.execute("INSERT INTO user_decompositions (character,parts,updated_at,deleted_at,base_json,dirty) VALUES (?,?,?,?,'{}',0)",
                                    (r["character"], r["parts"], utc_to_local(r.get("updated_at")), dele))
                    self.stats["pulled"] += 1
                elif loc["parts"] != r["parts"] or (loc["deleted_at"] is None) != (dele is None):
                    self.db.execute("UPDATE user_decompositions SET parts=?, deleted_at=?, updated_at=?, base_json='{}', dirty=0 WHERE character=?",
                                    (r["parts"], dele, utc_to_local(r.get("updated_at")), r["character"]))
                    self.stats["pulled"] += 1
        if rows:
            self._set_state(key, max(r["updated_at"] for r in rows))



def reset_sync_state(db_path=None, new_ids=False):
    """Ngắt liên kết đồng bộ của DB cục bộ: quên tài khoản/mốc/chữ ký/bản gốc; MỌI hàng coi là chưa gửi.
    Dùng khi (a) chuyển sang tài khoản/máy chủ khác, (b) sau khi khôi phục backup. Dữ liệu trên máy không bị xoá;
    lần đồng bộ kế tiếp là 'lần đầu' (gộp theo id, hàng trùng id được hợp nhất theo từng trường).
    new_ids=True: cấp ID MỚI cho mọi hàng — bắt buộc khi gửi sang tài khoản khác trên CÙNG máy chủ (ID là khoá chính toàn cục,
    ID đã thuộc tài khoản cũ nên tài khoản mới không ghi được)."""
    from database import db as dbmod
    path = db_path or dbmod.DB_PATH
    c = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        if new_ids:
            c.execute("PRAGMA foreign_keys = OFF")
        c.execute("BEGIN IMMEDIATE")
        have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def cols(t):
            return {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
        for t in ("_sync_state", "_sync_tombstones"):
            if t in have:
                c.execute(f"DELETE FROM {t}")
        for t in ("cards", "decks", "radicals", "deck_categories", "deck_cards", "radical_cards", "user_decompositions",
                  "grammar_points", "translations", "conj_forms", "conj_verbs", "conj_cells"):
            if t not in have:
                continue
            cs = cols(t); sets = [f"{k}=NULL" for k in ("base_json", "server_version") if k in cs]
            if "dirty" in cs:
                sets.append("dirty=1")
            if sets:
                c.execute(f"UPDATE {t} SET {', '.join(sets)}")
        if "study_sessions" in have and "dirty" in cols("study_sessions"):
            c.execute("UPDATE study_sessions SET dirty=2")      # lịch sử: gửi thẳng, không tính lại SRS
        if new_ids:
            for t in ("deck_categories", "decks", "radicals", "cards", "deck_cards", "radical_cards", "study_sessions",
                      "grammar_points", "translations", "conj_forms", "conj_verbs"):
                if t not in have:
                    continue
                for (old,) in c.execute(f"SELECT id FROM {t}").fetchall():
                    new = uuid7()
                    c.execute(f"UPDATE {t} SET id=? WHERE id=?", (new, old))
                    for child, col in _FK_COLUMNS.get(t, ()):
                        if child in have:
                            c.execute(f"UPDATE {child} SET {col}=? WHERE {col}=?", (new, old))
        c.execute("COMMIT")
    except BaseException:
        try:
            c.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        c.close()


_FK_COLUMNS = {
    "deck_categories": (("decks", "category_id"),),
    "decks": (("deck_cards", "deck_id"),),
    "radicals": (("radical_cards", "radical_id"),),
    "cards": (("deck_cards", "card_id"), ("radical_cards", "card_id"), ("study_sessions", "card_id")),
    "conj_forms": (("conj_cells", "form_id"),),
    "conj_verbs": (("conj_cells", "verb_id"),),
}
