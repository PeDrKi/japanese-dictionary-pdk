"""
Regression tests cho các lỗi tìm thấy khi rà soát:
  1. xóa/khôi phục/★/đổi trạng thái/ôn tập KHÔNG cập nhật updated_at → sync bỏ qua, bản xóa bị "hồi sinh"
  2. sync không mang theo tiến độ SRS (interval / ease / due)
  3. sync không gộp deck_categories → category_id mồ côi
  4. sync chèn deck_cards / radical_cards / study_sessions với id = NULL
  5. backup chép file .db thô (thiếu dữ liệu nằm trong WAL); restore bị file -wal cũ phá
"""
import json
import sqlite3
import time
import zipfile

import pytest

from database import db as db_module
from database import models
from database import _common
from infrastructure import backup as bk
from infrastructure.id_gen import uuid7
from infrastructure.supabase_sync import SupabaseSync
from tests.conftest import card_payload


def _use(path, monkeypatch):
    _common.close_thread_connection()
    monkeypatch.setattr(db_module, "DB_PATH", str(path))


def _row(path, sql, args=()):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    try:
        return c.execute(sql, args).fetchone()
    finally:
        c.close()


def _sync():
    return SupabaseSync(supabase_url="unused", supabase_key="unused")


@pytest.fixture
def pair(tmp_path, monkeypatch):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    for p in (a, b):
        _use(p, monkeypatch)
        db_module.init_db(seed_sample_data=False)
        _common.close_thread_connection()
    return a, b


def _make_synced_card(pair, monkeypatch):
    """Tạo 1 thẻ ở A rồi sao chép sang B (trạng thái 'đã đồng bộ'). Trả về (id, a, b)."""
    a, b = pair
    _use(a, monkeypatch)
    cid = models.add_card(card_payload(character="猫", meaning_vi="mèo"))
    _common.close_thread_connection()
    SupabaseSync._sqlite_backup(str(a), str(b))
    return cid, a, b


# ── 1. updated_at ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("op", ["delete", "favorite", "status", "bulk_delete", "study", "bulk_fav"])
def test_card_mutations_bump_updated_at(pair, monkeypatch, op):
    cid, a, _ = _make_synced_card(pair, monkeypatch)
    before = _row(a, "SELECT updated_at FROM cards")["updated_at"]
    time.sleep(1.1)  # updated_at có độ phân giải 1 giây
    _use(a, monkeypatch)
    {
        "delete":      lambda: models.soft_delete_card(cid),
        "favorite":    lambda: models.toggle_favorite(cid),
        "status":      lambda: models.bulk_update_status([cid], "known"),
        "bulk_delete": lambda: models.bulk_soft_delete([cid]),
        "bulk_fav":    lambda: models.bulk_toggle_favorite([cid]),
        "study":       lambda: models.log_study(cid, "correct"),
    }[op]()
    _common.close_thread_connection()
    assert _row(a, "SELECT updated_at FROM cards")["updated_at"] > before


def test_restore_bumps_updated_at(pair, monkeypatch):
    cid, a, _ = _make_synced_card(pair, monkeypatch)
    _use(a, monkeypatch)
    models.soft_delete_card(cid)
    _common.close_thread_connection()
    mid = _row(a, "SELECT updated_at FROM cards")["updated_at"]
    time.sleep(1.1)
    _use(a, monkeypatch)
    models.restore_card(cid)
    _common.close_thread_connection()
    assert _row(a, "SELECT updated_at FROM cards")["updated_at"] > mid


def test_delete_on_one_device_propagates_through_merge(pair, monkeypatch):
    cid, a, b = _make_synced_card(pair, monkeypatch)
    time.sleep(1.1)
    _use(a, monkeypatch)
    models.soft_delete_card(cid)
    _common.close_thread_connection()
    _sync()._merge(str(b), str(a))          # B kéo từ A
    assert _row(b, "SELECT deleted_at FROM cards")["deleted_at"] is not None


# ── 2. SRS ────────────────────────────────────────────────────────────────────

def test_srs_progress_syncs_to_other_device(pair, monkeypatch):
    cid, a, b = _make_synced_card(pair, monkeypatch)
    time.sleep(1.1)
    _use(a, monkeypatch)
    models.log_study(cid, "correct")
    models.log_study(cid, "correct")
    _common.close_thread_connection()
    want = dict(_row(a, "SELECT status, srs_interval, srs_ease, srs_due_date FROM cards"))
    _sync()._merge(str(b), str(a))
    assert dict(_row(b, "SELECT status, srs_interval, srs_ease, srs_due_date FROM cards")) == want


def test_new_card_pulled_keeps_its_srs_state(pair, monkeypatch):
    a, b = pair
    cid = uuid7()
    c = sqlite3.connect(a)
    c.execute("INSERT INTO cards (id,type,character,meaning_vi,status,srs_interval,srs_ease,srs_due_date) "
              "VALUES (?,?,?,?,?,?,?,?)", (cid, "vocab", "犬", "chó", "known", 30, 2.8, "2030-01-01"))
    c.commit(); c.close()
    _sync()._merge(str(b), str(a))
    r = _row(b, "SELECT srs_interval, srs_ease, srs_due_date FROM cards")
    assert (r["srs_interval"], r["srs_ease"], r["srs_due_date"]) == (30, 2.8, "2030-01-01")


# ── 3. deck_categories ────────────────────────────────────────────────────────

def test_categories_are_merged_and_decks_point_at_local_ids(pair):
    a, b = pair
    # B đã có danh mục cùng tên nhưng id khác; A có thêm 1 danh mục riêng
    cat_a1, cat_a2, cat_b1, deck1, deck2 = (uuid7() for _ in range(5))
    ca = sqlite3.connect(a)
    ca.execute("INSERT INTO deck_categories (id,name) VALUES (?,?)", (cat_a1, "N5"))
    ca.execute("INSERT INTO deck_categories (id,name) VALUES (?,?)", (cat_a2, "Du lịch"))
    ca.execute("INSERT INTO decks (id,name,category_id) VALUES (?,?,?)", (deck1, "Kanji 1", cat_a1))
    ca.execute("INSERT INTO decks (id,name,category_id) VALUES (?,?,?)", (deck2, "Taxi", cat_a2))
    ca.commit(); ca.close()
    cb = sqlite3.connect(b)
    cb.execute("INSERT INTO deck_categories (id,name) VALUES (?,?)", (cat_b1, "N5"))
    cb.commit(); cb.close()

    _sync()._merge(str(b), str(a))

    c = sqlite3.connect(b); c.row_factory = sqlite3.Row
    cats = {r["name"]: r["id"] for r in c.execute("SELECT id,name FROM deck_categories")}
    assert set(cats) == {"N5", "Du lịch"} and cats["N5"] == cat_b1      # không nhân đôi
    deck_cat = {r["name"]: r["category_id"] for r in c.execute("SELECT name, category_id FROM decks")}
    assert deck_cat == {"Kanji 1": cat_b1, "Taxi": cats["Du lịch"]}
    assert c.execute("SELECT COUNT(*) FROM decks WHERE category_id NOT IN (SELECT id FROM deck_categories)").fetchone()[0] == 0
    c.close()


# ── 4. id NULL ────────────────────────────────────────────────────────────────

def test_pulled_link_and_session_rows_get_real_ids(pair, monkeypatch):
    a, b = pair
    card, deck, rad = uuid7(), uuid7(), uuid7()
    c = sqlite3.connect(a)
    c.execute("INSERT INTO cards (id,type,character,meaning_vi) VALUES (?,?,?,?)", (card, "kanji", "水", "nước"))
    c.execute("INSERT INTO decks (id,name) VALUES (?,?)", (deck, "D"))
    c.execute("INSERT INTO deck_cards (id,deck_id,card_id) VALUES (?,?,?)", (uuid7(), deck, card))
    c.execute("INSERT INTO radicals (id,character) VALUES (?,?)", (rad, "氵"))
    c.execute("INSERT INTO radical_cards (id,radical_id,card_id) VALUES (?,?,?)", (uuid7(), rad, card))
    c.execute("INSERT INTO study_sessions (id,card_id,result) VALUES (?,?,?)", (uuid7(), card, "correct"))
    c.commit(); c.close()
    _sync()._merge(str(b), str(a))
    for t in ("deck_cards", "radical_cards", "study_sessions"):
        assert _row(b, f"SELECT COUNT(*) n FROM {t}")["n"] == 1
        assert _row(b, f"SELECT COUNT(*) n FROM {t} WHERE id IS NULL")["n"] == 0, t


def test_init_db_backfills_null_ids_from_old_syncs(tmp_path, monkeypatch):
    p = tmp_path / "old.db"
    _use(p, monkeypatch)
    db_module.init_db(seed_sample_data=False)
    card = uuid7()
    c = sqlite3.connect(p)
    c.execute("INSERT INTO cards (id,type,character,meaning_vi) VALUES (?,?,?,?)", (card, "kanji", "水", "nước"))
    c.execute("INSERT INTO study_sessions (id,card_id,result) VALUES (NULL,?,?)", (card, "correct"))
    c.execute("INSERT INTO study_sessions (id,card_id,result) VALUES (NULL,?,?)", (card, "incorrect"))
    c.commit(); c.close()
    db_module.init_db(seed_sample_data=False)
    ids = [r[0] for r in sqlite3.connect(p).execute("SELECT id FROM study_sessions")]
    assert len(ids) == 2 and all(ids) and len(set(ids)) == 2


# ── 5. backup / restore ───────────────────────────────────────────────────────

@pytest.fixture
def live_db(tmp_path, monkeypatch):
    """Một DB đang được 'app' giữ kết nối mở ở chế độ WAL, dữ liệu mới nằm trong file -wal."""
    db = tmp_path / "japanese.db"
    monkeypatch.setattr(bk, "_DB_PATH", str(db))
    monkeypatch.setattr(bk, "_SETTINGS_PATH", str(tmp_path / "settings.json"))
    conn = sqlite3.connect(db, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=wal")
    conn.execute("CREATE TABLE cards (x)")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    yield conn, db, tmp_path
    conn.close()


def test_backup_contains_data_still_in_wal(live_db):
    conn, db, tmp = live_db
    for i in range(5):
        conn.execute("INSERT INTO cards VALUES (?)", (i,))
    conn.commit()
    out = tmp / "out"; out.mkdir()
    path, err = bk.create_backup(str(out))
    assert err == ""
    with zipfile.ZipFile(path) as z:
        z.extract("japanese.db", tmp / "x")
    assert sqlite3.connect(tmp / "x" / "japanese.db").execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 5


def test_backup_does_not_leak_supabase_credentials(live_db):
    conn, db, tmp = live_db
    (tmp / "settings.json").write_text(json.dumps({"theme": "dark", "supabase_key": "SECRET", "supabase_url": "https://x.supabase.co"}))
    out = tmp / "out"; out.mkdir()
    path, _ = bk.create_backup(str(out))
    with zipfile.ZipFile(path) as z:
        data = json.loads(z.read("settings.json"))
    assert data == {"theme": "dark"}


def test_restore_replaces_data_and_survives_app_exit(live_db):
    conn, db, tmp = live_db
    for i in range(3):
        conn.execute("INSERT INTO cards VALUES (?)", (i,))
    conn.commit()
    out = tmp / "out"; out.mkdir()
    path, _ = bk.create_backup(str(out))          # backup có 3 dòng
    for i in range(3, 9):                         # dùng tiếp: 9 dòng
        conn.execute("INSERT INTO cards VALUES (?)", (i,))
    conn.commit()

    ok, msg = bk.restore_backup(path)
    assert ok, msg
    conn.close()                                  # app thoát: WAL cũ KHÔNG được áp lên bản khôi phục
    c = sqlite3.connect(db)
    assert c.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 3
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_restore_keeps_current_supabase_settings(live_db):
    conn, db, tmp = live_db
    (tmp / "settings.json").write_text(json.dumps({"theme": "dark", "supabase_key": "MINE"}))
    out = tmp / "out"; out.mkdir()
    path, _ = bk.create_backup(str(out))
    (tmp / "settings.json").write_text(json.dumps({"theme": "light", "supabase_key": "MINE"}))
    ok, _ = bk.restore_backup(path)
    assert ok
    s = json.loads((tmp / "settings.json").read_text())
    assert s["supabase_key"] == "MINE" and s["theme"] == "dark"


def test_restore_rejects_non_database_zip(live_db):
    conn, db, tmp = live_db
    bad = tmp / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("japanese.db", b"not a sqlite file at all")
    ok, msg = bk.restore_backup(str(bad))
    assert not ok
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0   # DB đang dùng nguyên vẹn
