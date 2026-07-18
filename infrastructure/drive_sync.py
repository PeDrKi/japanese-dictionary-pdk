"""
infrastructure/drive_sync.py — 2-chiều sync japanese.db với Google Drive.
Moved from utils/ (Stage: utils/ cleanup) since this does real
sqlite3/file/network I/O.

Chiến lược : Last-write-wins theo cột updated_at.
Xác thực   : OAuth2 — đăng nhập Google qua browser lần đầu,
              token được lưu vào token.json cạnh DB.

Yêu cầu:
    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

import sqlite3
import shutil
import os
import logging
import tempfile
from datetime import datetime
from database.db import DB_PATH

logger = logging.getLogger(__name__)

DEFAULT_DRIVE_FILENAME = "japanese.db"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Token lưu cạnh DB cho tiện
_DB_DIR    = os.path.dirname(os.path.abspath(DB_PATH))
TOKEN_PATH = os.path.join(_DB_DIR, "drive_token.json")


class DriveSync:
    """
    Sync 2 chiều giữa local DB và file trên Google Drive (My Drive).

    Params:
        client_secret_path — đường dẫn OAuth2 client_secret JSON
                             (tải từ Google Cloud Console)
        drive_filename     — tên file trên Drive (mặc định: japanese.db)
        drive_folder_id    — ID thư mục Drive (None = root My Drive)
        progress_cb        — callback(message: str) để cập nhật UI
    """

    def __init__(self, client_secret_path: str,
                 drive_filename: str = DEFAULT_DRIVE_FILENAME,
                 drive_folder_id: str | None = None,
                 progress_cb=None):
        self.client_secret_path = client_secret_path
        self.drive_filename     = drive_filename
        self.drive_folder_id    = drive_folder_id
        self.progress_cb        = progress_cb or (lambda msg: None)

    # ── Public entry point ────────────────────────────────────────────────────

    def sync(self) -> tuple[bool, dict, str]:
        """
        Trả về (success, stats_dict, error_message).
        stats: {pushed, pulled, conflicts_resolved, skipped}
        """
        try:
            return self._run_sync()
        except ImportError as e:
            msg = (f"Thiếu thư viện: {e}\n"
                   "Chạy:  pip install google-api-python-client "
                   "google-auth-oauthlib google-auth-httplib2")
            logger.error(msg)
            return False, {}, msg
        except Exception as e:
            logger.exception("Sync failed")
            return False, {}, str(e)

    def revoke_token(self):
        """Xoá token đã lưu — cần đăng nhập lại lần sau."""
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
            logger.info("Token revoked")

    # ── Core sync logic ───────────────────────────────────────────────────────

    def _run_sync(self) -> tuple[bool, dict, str]:
        self._log("🔑 Đăng nhập Google...")
        service = self._build_service()

        self._log("🔍 Tìm file trên Google Drive...")
        file_id = self._find_drive_file(service)

        with tempfile.TemporaryDirectory() as tmp:
            remote_path = os.path.join(tmp, "remote.db")

            if file_id:
                self._log("⬇️  Tải DB từ Drive...")
                self._download(service, file_id, remote_path)
                self._log("🔀 Đang merge dữ liệu...")
                stats = self._merge(local_path=DB_PATH,
                                    remote_path=remote_path)
            else:
                self._log("📭 Chưa có file trên Drive — sẽ upload lần đầu.")
                stats = {"pushed": 0, "pulled": 0,
                         "conflicts_resolved": 0, "skipped": 0}

            self._log("⬆️  Upload DB đã merge lên Drive...")
            self._upload(service, DB_PATH, file_id)

        summary = (f"✅ Sync hoàn tất  |  "
                   f"Đẩy lên: {stats['pushed']}  "
                   f"Kéo về: {stats['pulled']}  "
                   f"Conflict: {stats['conflicts_resolved']}")
        self._log(summary)
        return True, stats, ""

    # ── OAuth2 auth ───────────────────────────────────────────────────────────

    def _build_service(self):
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None

        # Load token đã lưu
        if os.path.exists(TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(
                    TOKEN_PATH, SCOPES)
            except Exception:
                creds = None

        # Refresh nếu hết hạn
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_token(creds)
                self._log("🔄 Token đã được làm mới tự động.")
            except Exception:
                creds = None

        # Chưa có hoặc không refresh được → mở browser đăng nhập
        if not creds or not creds.valid:
            self._log("🌐 Đang mở browser để đăng nhập Google...")
            flow = InstalledAppFlow.from_client_secrets_file(
                self.client_secret_path, SCOPES)
            # run_local_server mở browser và tự bắt callback
            creds = flow.run_local_server(
                port=0,
                success_message=(
                    "Đăng nhập thành công! "
                    "Bạn có thể đóng tab này và quay lại app."
                ),
                open_browser=True,
            )
            self._save_token(creds)
            self._log("✅ Đăng nhập thành công, token đã lưu.")

        return build("drive", "v3", credentials=creds, cache_discovery=False)

    @staticmethod
    def _save_token(creds):
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        logger.info(f"Token saved to {TOKEN_PATH}")

    # ── Google Drive helpers ──────────────────────────────────────────────────

    def _find_drive_file(self, service) -> str | None:
        q = f"name='{self.drive_filename}' and trashed=false"
        if self.drive_folder_id:
            q += f" and '{self.drive_folder_id}' in parents"

        resp = service.files().list(
            q=q, spaces="drive",
            fields="files(id, name)",
            pageSize=5
        ).execute()

        files = resp.get("files", [])
        if files:
            logger.info(f"Found Drive file id={files[0]['id']}")
            return files[0]["id"]
        return None

    def _download(self, service, file_id: str, dest_path: str):
        from googleapiclient.http import MediaIoBaseDownload
        import io

        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        dl  = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        with open(dest_path, "wb") as f:
            f.write(buf.getvalue())
        logger.info(f"Downloaded {len(buf.getvalue())} bytes")

    def _upload(self, service, src_path: str, file_id: str | None):
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(
            src_path,
            mimetype="application/x-sqlite3",
            resumable=False
        )

        if file_id:
            service.files().update(
                fileId=file_id,
                media_body=media,
            ).execute()
            logger.info(f"Updated Drive file id={file_id}")
        else:
            meta = {"name": self.drive_filename}
            if self.drive_folder_id:
                meta["parents"] = [self.drive_folder_id]
            f = service.files().create(
                body=meta,
                media_body=media,
                fields="id",
            ).execute()
            logger.info(f"Created Drive file id={f['id']}")

    # ── Merge logic ───────────────────────────────────────────────────────────

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
