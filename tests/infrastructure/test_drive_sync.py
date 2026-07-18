"""
Tests for infrastructure/drive_sync.py's merge logic — specifically the
radicals / radical_cards / user_decompositions merges added so the "🧩 Bộ
thủ" and "✏️ Sửa bộ phận" features actually sync via Google Drive (they
were silently missing from _merge() before).

No network/OAuth involved: DriveSync._merge() takes two plain sqlite file
paths and merges local<-remote directly, so these tests exercise it the
same way _run_sync() does internally, just without Google Drive in the
loop.
"""
import sqlite3
import pytest

from database import db as db_module
from infrastructure.drive_sync import DriveSync


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


def make_sync() -> DriveSync:
    return DriveSync(client_secret_path="unused-in-these-tests")


def insert_card(path, character="暗", type_="kanji"):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO cards (type, character, meaning_vi, created_at, updated_at) "
        "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
        (type_, character, "test"))
    conn.commit()
    card_id = conn.execute("SELECT id FROM cards WHERE character=?", (character,)).fetchone()[0]
    conn.close()
    return card_id


# ── radicals ─────────────────────────────────────────────────────────────────

def test_pulls_a_radical_that_only_exists_on_remote(two_dbs):
    local_path, remote_path = two_dbs
    conn = sqlite3.connect(remote_path)
    conn.execute("INSERT INTO radicals (character, name, color, sort_order) VALUES (?,?,?,?)",
                 ("日", "bộ Nhật", "#4A90D9", 0))
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
        conn.execute("INSERT INTO radicals (character, name) VALUES (?,?)", ("日", "bộ Nhật"))
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
    conn.execute("INSERT INTO radicals (character, name) VALUES (?,?)", ("日", "bộ Nhật"))
    radical_id = conn.execute("SELECT id FROM radicals WHERE character=?", ("日",)).fetchone()[0]
    conn.execute("INSERT INTO radical_cards (radical_id, card_id) VALUES (?,?)",
                 (radical_id, remote_card_id))
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
    conn.execute("INSERT INTO radicals (character, name) VALUES (?,?)", ("日", "bộ Nhật"))
    radical_id = conn.execute("SELECT id FROM radicals WHERE character=?", ("日",)).fetchone()[0]
    # Orphaned reference — no matching row in `cards` on either side, so
    # _merge_cards (which runs first) has nothing to pull for it either.
    conn.execute("INSERT INTO radical_cards (radical_id, card_id) VALUES (?, 999999)",
                 (radical_id,))
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
