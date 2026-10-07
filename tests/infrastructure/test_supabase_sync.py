"""
Tests for infrastructure/supabase_sync.py's merge logic — specifically the
radicals / radical_cards / user_decompositions merges added so the "🧩 Bộ
thủ" and "✏️ Sửa bộ phận" features actually sync via Supabase (they
were silently missing from _merge() before).

No network/OAuth involved: SupabaseSync._merge() takes two plain sqlite file
paths and merges local<-remote directly, so these tests exercise it the
same way _run_sync() does internally, just without Supabase in the
loop.
"""
import sqlite3
import pytest

from database import db as db_module
from infrastructure.supabase_sync import SupabaseSync
from infrastructure.id_gen import uuid7


@pytest.fixture
def two_dbs(tmp_path, monkeypatch):
    """Two independently-initialized (real schema) throwaway DB files:
    local.db and remote.db."""
    from database import models

    local_path = tmp_path / "local.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(local_path))
    models.close_thread_connection()
    db_module.init_db(seed_sample_data=False)
    models.close_thread_connection()

    remote_path = tmp_path / "remote.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(remote_path))
    models.close_thread_connection()
    db_module.init_db(seed_sample_data=False)
    models.close_thread_connection()

    return str(local_path), str(remote_path)


def make_sync() -> SupabaseSync:
    return SupabaseSync(supabase_url="unused-in-these-tests", supabase_key="unused")


def insert_card(path, character="暗", type_="kanji"):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO cards (id, type, character, meaning_vi, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
        (uuid7(), type_, character, "test"))
    conn.commit()
    card_id = conn.execute("SELECT id FROM cards WHERE character=?", (character,)).fetchone()[0]
    conn.close()
    return card_id


# ── radicals ─────────────────────────────────────────────────────────────────

def test_pulls_a_radical_that_only_exists_on_remote(two_dbs):
    local_path, remote_path = two_dbs
    conn = sqlite3.connect(remote_path)
    conn.execute("INSERT INTO radicals (id, character, name, color, sort_order) VALUES (?,?,?,?,?)",
                 (uuid7(), "日", "bộ Nhật", "#4A90D9", 0))
    conn.commit(); conn.close()

    stats = make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute("SELECT * FROM radicals WHERE character=?", ("日",)).fetchone()
    local.close()
    assert row is not None
    assert stats["pulled"] >= 1


def test_does_not_duplicate_a_radical_that_exists_on_both(two_dbs):
    local_path, remote_path = two_dbs
    for path in (local_path, remote_path):
        conn = sqlite3.connect(path)
        conn.execute("INSERT INTO radicals (id, character, name) VALUES (?,?,?)", (uuid7(), "日", "bộ Nhật"))
        conn.commit(); conn.close()

    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    count = local.execute("SELECT COUNT(*) FROM radicals WHERE character=?", ("日",)).fetchone()[0]
    local.close()
    assert count == 1


# ── radical_cards (depends on radicals + cards already matching) ──────────────

def test_pulls_radical_card_assignment_when_both_sides_exist_locally(two_dbs):
    local_path, remote_path = two_dbs

    # Card must exist on both sides with a matching character (sync doesn't
    # invent cards here — _merge_cards, tested elsewhere, handles that part).
    local_card_id  = insert_card(local_path, "暗")
    remote_card_id = insert_card(remote_path, "暗")

    conn = sqlite3.connect(remote_path)
    conn.execute("INSERT INTO radicals (id, character, name) VALUES (?,?,?)", (uuid7(), "日", "bộ Nhật"))
    radical_id = conn.execute("SELECT id FROM radicals WHERE character=?", ("日",)).fetchone()[0]
    conn.execute("INSERT INTO radical_cards (id, radical_id, card_id) VALUES (?,?,?)",
                 (uuid7(), radical_id, remote_card_id))
    conn.commit(); conn.close()

    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute(
        "SELECT c.character FROM radical_cards rc "
        "JOIN radicals r ON r.id = rc.radical_id "
        "JOIN cards c ON c.id = rc.card_id "
        "WHERE r.character=?", ("日",)
    ).fetchone()
    local.close()
    assert row is not None and row[0] == "暗"


def test_skips_radical_card_assignment_when_card_missing_locally(two_dbs):
    local_path, remote_path = two_dbs

    conn = sqlite3.connect(remote_path)
    conn.execute("INSERT INTO radicals (id, character, name) VALUES (?,?,?)", (uuid7(), "日", "bộ Nhật"))
    radical_id = conn.execute("SELECT id FROM radicals WHERE character=?", ("日",)).fetchone()[0]
    # Orphaned reference — no matching row in `cards` on either side, so
    # _merge_cards (which runs first) has nothing to pull for it either.
    conn.execute("INSERT INTO radical_cards (id, radical_id, card_id) VALUES (?, ?, ?)",
                 (uuid7(), radical_id, "id-nao-do-khong-ton-tai"))
    conn.commit(); conn.close()

    # Must not raise even though the referenced card doesn't exist anywhere.
    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    count = local.execute("SELECT COUNT(*) FROM radical_cards").fetchone()[0]
    local.close()
    assert count == 0


# ── user_decompositions ────────────────────────────────────────────────────────

def test_pulls_a_user_decomposition_that_only_exists_on_remote(two_dbs):
    local_path, remote_path = two_dbs
    conn = sqlite3.connect(remote_path)
    conn.execute("INSERT INTO user_decompositions (character, parts) VALUES (?,?)", ("暗", "日音"))
    conn.commit(); conn.close()

    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute("SELECT parts FROM user_decompositions WHERE character=?", ("暗",)).fetchone()
    local.close()
    assert row is not None and row[0] == "日音"


def test_newer_remote_decomposition_wins_conflict(two_dbs):
    local_path, remote_path = two_dbs
    conn = sqlite3.connect(local_path)
    conn.execute(
        "INSERT INTO user_decompositions (character, parts, updated_at) VALUES (?,?,?)",
        ("暗", "OLD", "2020-01-01 00:00:00"))
    conn.commit(); conn.close()

    conn = sqlite3.connect(remote_path)
    conn.execute(
        "INSERT INTO user_decompositions (character, parts, updated_at) VALUES (?,?,?)",
        ("暗", "NEW", "2030-01-01 00:00:00"))
    conn.commit(); conn.close()

    stats = make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute("SELECT parts FROM user_decompositions WHERE character=?", ("暗",)).fetchone()
    local.close()
    assert row[0] == "NEW"
    assert stats["conflicts_resolved"] >= 1


def test_newer_local_decomposition_is_kept(two_dbs):
    local_path, remote_path = two_dbs
    conn = sqlite3.connect(local_path)
    conn.execute(
        "INSERT INTO user_decompositions (character, parts, updated_at) VALUES (?,?,?)",
        ("暗", "MINE", "2030-01-01 00:00:00"))
    conn.commit(); conn.close()

    conn = sqlite3.connect(remote_path)
    conn.execute(
        "INSERT INTO user_decompositions (character, parts, updated_at) VALUES (?,?,?)",
        ("暗", "OLDER", "2020-01-01 00:00:00"))
    conn.commit(); conn.close()

    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute("SELECT parts FROM user_decompositions WHERE character=?", ("暗",)).fetchone()
    local.close()
    assert row[0] == "MINE"


# ── backward compatibility: remote DB predates these tables ───────────────────

def test_merge_does_not_crash_when_remote_db_predates_these_tables(two_dbs):
    local_path, remote_path = two_dbs
    conn = sqlite3.connect(remote_path)
    conn.execute("DROP TABLE radicals")
    conn.execute("DROP TABLE radical_cards")
    conn.execute("DROP TABLE user_decompositions")
    conn.commit(); conn.close()

    # Must complete without raising, and must not touch local's (still
    # present) tables.
    stats = make_sync()._merge(local_path=local_path, remote_path=remote_path)
    assert isinstance(stats, dict)

    local = sqlite3.connect(local_path)
    local.execute("SELECT COUNT(*) FROM radicals").fetchone()  # table still exists locally
    local.close()


# ── xóa mềm không bị "hồi sinh" khi merge (rủi ro #1 đã khắc phục) ────────────

def test_deleting_a_deck_locally_survives_a_sync_from_stale_remote(two_dbs):
    """Deck vẫn còn 'mới hơn' (deleted_at) trên local sau khi merge với 1
    bản remote CŨ (trước khi deck từng được xóa) — deck KHÔNG được hồi
    sinh lại, đúng như kỳ vọng của cơ chế xóa mềm."""
    local_path, remote_path = two_dbs

    # Deck tồn tại (chưa xóa) ở CẢ 2 bên với cùng id + created_at, remote
    # đại diện cho 1 bản snapshot CŨ (trước khi deck bị xóa ở máy hiện tại).
    for path in (local_path, remote_path):
        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT INTO decks (id, name, created_at, updated_at) VALUES (?,?,?,?)",
            (uuid7(), "Ôn thi N3", "2025-01-01 00:00:00", "2025-01-01 00:00:00"))
        conn.commit(); conn.close()

    # Xóa mềm ở local, với updated_at MỚI hơn remote.
    conn = sqlite3.connect(local_path)
    conn.execute(
        "UPDATE decks SET deleted_at=?, updated_at=? WHERE name=?",
        ("2026-06-01 00:00:00", "2026-06-01 00:00:00", "Ôn thi N3"))
    conn.commit(); conn.close()

    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute(
        "SELECT deleted_at FROM decks WHERE name=?", ("Ôn thi N3",)).fetchone()
    local.close()
    assert row is not None and row[0] is not None, (
        "Deck đã bị hồi sinh sau sync — lỗi này đúng là rủi ro #1 mà ta muốn khắc phục.")


def test_deleting_a_radical_locally_survives_a_sync(two_dbs):
    local_path, remote_path = two_dbs
    for path in (local_path, remote_path):
        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT INTO radicals (id, character, name, created_at, updated_at) VALUES (?,?,?,?,?)",
            (uuid7(), "水", "bộ Thủy", "2025-01-01 00:00:00", "2025-01-01 00:00:00"))
        conn.commit(); conn.close()

    conn = sqlite3.connect(local_path)
    conn.execute(
        "UPDATE radicals SET deleted_at=?, updated_at=? WHERE character=?",
        ("2026-06-01 00:00:00", "2026-06-01 00:00:00", "水"))
    conn.commit(); conn.close()

    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute(
        "SELECT deleted_at FROM radicals WHERE character=?", ("水",)).fetchone()
    local.close()
    assert row is not None and row[0] is not None


def test_removing_a_card_from_a_deck_survives_a_sync(two_dbs):
    """Gỡ 1 thẻ khỏi deck (soft-delete deck_cards) không bị thêm lại khi
    remote vẫn còn bản ghi liên kết cũ (chưa gỡ)."""
    local_path, remote_path = two_dbs
    card_id = insert_card(local_path, "暗")
    insert_card(remote_path, "暗")  # cùng id do fresh db, xem ghi chú insert_card

    for path in (local_path, remote_path):
        conn = sqlite3.connect(path)
        conn.execute("INSERT INTO decks (id, name, created_at, updated_at) VALUES (?,?,?,?)",
                     (uuid7(), "Deck A", "2025-01-01 00:00:00", "2025-01-01 00:00:00"))
        deck_id = conn.execute("SELECT id FROM decks WHERE name='Deck A'").fetchone()[0]
        conn.execute(
            "INSERT INTO deck_cards (id, deck_id, card_id, added_at, updated_at) VALUES (?,?,?,?,?)",
            (uuid7(), deck_id, card_id, "2025-01-01 00:00:00", "2025-01-01 00:00:00"))
        conn.commit(); conn.close()

    # Gỡ thẻ khỏi deck ở local, updated_at mới hơn.
    conn = sqlite3.connect(local_path)
    conn.execute(
        "UPDATE deck_cards SET deleted_at=?, updated_at=? WHERE card_id=?",
        ("2026-06-01 00:00:00", "2026-06-01 00:00:00", card_id))
    conn.commit(); conn.close()

    make_sync()._merge(local_path=local_path, remote_path=remote_path)

    local = sqlite3.connect(local_path)
    row = local.execute(
        "SELECT deleted_at FROM deck_cards WHERE card_id=?", (card_id,)).fetchone()
    local.close()
    assert row is not None and row[0] is not None


# ── phát hiện trùng ID (rủi ro #4 — cảnh báo thay vì mất dữ liệu) ────────────

def test_id_collision_on_cards_keeps_both_records_instead_of_overwriting(two_dbs):
    """2 thiết bị độc lập tạo 2 thẻ KHÁC NHAU nhưng cùng id (vd sau khi
    reset_db.py). Kỳ vọng: KHÔNG ghi đè mất 1 bên — cả 2 nội dung đều còn
    trong local sau merge (bên collision được thêm là dòng mới)."""
    local_path, remote_path = two_dbs

    conn = sqlite3.connect(local_path)
    conn.execute(
        "INSERT INTO cards (id, type, character, meaning_vi, created_at, updated_at) "
        "VALUES (1,'kanji','水','nước','2025-01-01 00:00:00','2025-01-01 00:00:00')")
    conn.commit(); conn.close()

    conn = sqlite3.connect(remote_path)
    conn.execute(
        "INSERT INTO cards (id, type, character, meaning_vi, created_at, updated_at) "
        "VALUES (1,'kanji','火','lửa','2025-06-01 00:00:00','2026-01-01 00:00:00')")
    conn.commit(); conn.close()

    stats = make_sync()._merge(local_path=local_path, remote_path=remote_path)

    assert stats["id_collisions"] == 1
    local = sqlite3.connect(local_path)
    chars = {r[0] for r in local.execute("SELECT character FROM cards").fetchall()}
    local.close()
    assert chars == {"水", "火"}, (
        f"Cả 2 thẻ khác nhau phải còn tồn tại sau merge, thấy: {chars}")


def test_same_card_edited_on_both_sides_is_not_flagged_as_collision(two_dbs):
    """Sửa nghĩa của CÙNG 1 thẻ (character/type/created_at không đổi) ở cả
    2 bên không được coi là trùng ID — phải merge bình thường theo
    updated_at, không nhân đôi thẻ."""
    local_path, remote_path = two_dbs

    for path, meaning, ts in (
        (local_path, "nước (cũ)", "2025-01-01 00:00:00"),
        (remote_path, "nước (mới)", "2026-01-01 00:00:00"),
    ):
        conn = sqlite3.connect(path)
        conn.execute(
            "INSERT INTO cards (id, type, character, meaning_vi, created_at, updated_at) "
            "VALUES (1,'kanji','水',?,'2024-01-01 00:00:00',?)",
            (meaning, ts))
        conn.commit(); conn.close()

    stats = make_sync()._merge(local_path=local_path, remote_path=remote_path)

    assert stats["id_collisions"] == 0
    local = sqlite3.connect(local_path)
    rows = local.execute("SELECT meaning_vi FROM cards").fetchall()
    local.close()
    assert len(rows) == 1 and rows[0][0] == "nước (mới)"


def test_id_collision_on_decks_keeps_both(two_dbs):
    local_path, remote_path = two_dbs
    conn = sqlite3.connect(local_path)
    conn.execute(
        "INSERT INTO decks (id, name, created_at, updated_at) "
        "VALUES (1,'Deck của tôi','2025-01-01 00:00:00','2025-01-01 00:00:00')")
    conn.commit(); conn.close()

    conn = sqlite3.connect(remote_path)
    conn.execute(
        "INSERT INTO decks (id, name, created_at, updated_at) "
        "VALUES (1,'Deck khác hẳn','2025-06-01 00:00:00','2026-01-01 00:00:00')")
    conn.commit(); conn.close()

    stats = make_sync()._merge(local_path=local_path, remote_path=remote_path)

    assert stats["id_collisions"] == 1
    local = sqlite3.connect(local_path)
    names = {r[0] for r in local.execute("SELECT name FROM decks").fetchall()}
    local.close()
    assert names == {"Deck của tôi", "Deck khác hẳn"}


# ── kiểm tra lệch đồng hồ (rủi ro #3) ──────────────────────────────────────────

def test_clock_skew_blocks_sync():
    from datetime import datetime, timedelta, timezone
    s = make_sync()
    server_time = datetime.now(timezone.utc)
    local_fake_time_way_off = server_time - timedelta(minutes=30)
    # Giả lập bằng cách so ngay với server_date do lệch — gọi thẳng hàm
    # kiểm tra với server_date đã bị đẩy lệch 30 phút so với "bây giờ".
    with pytest.raises(RuntimeError, match="lệch"):
        s._check_clock_skew(server_time + timedelta(minutes=30))


def test_clock_skew_within_tolerance_does_not_raise():
    from datetime import datetime, timedelta, timezone
    s = make_sync()
    s._check_clock_skew(datetime.now(timezone.utc) + timedelta(seconds=10))  # không raise


def test_clock_skew_none_server_date_does_not_raise():
    make_sync()._check_clock_skew(None)  # không lấy được giờ server -> bỏ qua, không raise
