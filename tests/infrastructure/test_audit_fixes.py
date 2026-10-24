"""Hồi quy cho đợt rà soát lần 2: đổi tài khoản, khôi phục backup, xoá danh mục từ nơi khác, UNIQUE chỉ tính hàng chưa xoá,
khoá đồng bộ, deadline, ghi settings an toàn, yêu thích hàng loạt."""
import os
import sqlite3

import pytest

from database import _common, db as db_module, models
from infrastructure import backup, cloud_sync, settings as settings_module
from infrastructure.cloud_sync import CloudSync, StaticAuth
from tests import pg_harness
from tests.conftest import card_payload
from tests.infrastructure.test_cloud_sync import Device, mk, remote, add_card  # noqa: F401  (mk là fixture)


def _sync_as(dev, user):
    _common.close_thread_connection()
    uid = pg_harness.USERS[user]
    return CloudSync(auth=StaticAuth(pg_harness.jwt(uid), uid), rest_url=dev.cloud.rest_url, db_path=dev.path).sync()


def test_account_switch_is_refused_then_reset_uploads_to_new_account(mk, cloud):
    d = mk()
    cid = add_card(d, character="猫")
    d.sync()
    add_card(d, character="犬")                       # chưa đồng bộ
    ok, stats, err = _sync_as(d, "b")
    assert not ok and stats.get("account_mismatch")
    # không mất gì: thẻ của tài khoản A vẫn ở máy, tài khoản B chưa nhận gì
    assert d.one("SELECT COUNT(*) n FROM cards")["n"] == 2
    assert remote(cloud, "cards", user="b") == []
    cloud_sync.reset_sync_state(d.path, new_ids=True)
    ok, stats, err = _sync_as(d, "b")
    assert ok, err
    assert {r["character"] for r in remote(cloud, "cards", user="b")} == {"猫", "犬"}
    assert d.one("SELECT COUNT(*) n FROM cards")["n"] == 2


def test_restore_backup_is_not_undone_by_next_sync(mk, cloud, tmp_path, monkeypatch):
    d = mk()
    ids = [add_card(d, character=c) for c in "猫犬鳥"]
    d.sync()
    monkeypatch.setattr(backup, "_DB_PATH", d.path)
    monkeypatch.setattr(backup, "_DB_DIR", str(tmp_path), raising=False)
    zpath, err = backup.create_backup(str(tmp_path))
    assert not err, err
    d.use()
    models.bulk_soft_delete(ids)
    d.sync()
    assert all(r["deleted_at"] for r in remote(cloud, "cards"))
    ok, msg = backup.restore_backup(zpath)
    assert ok, msg
    d.sync()
    assert all(r["deleted_at"] is None for r in remote(cloud, "cards")), "khôi phục bị sync ghi đè"
    assert d.one("SELECT COUNT(*) n FROM cards WHERE deleted_at IS NULL")["n"] == 3


def test_category_deleted_elsewhere_does_not_break_sync(mk, cloud):
    d = mk()
    d.use()
    cat = models.add_category("N5")
    deck = models.add_deck("A", category_id=cat)
    d.sync()
    d.sql("UPDATE decks SET description='sửa dở' WHERE id=?", (deck,))
    cloud.api("DELETE", f"/deck_categories?id=eq.{cat}")
    d.sync()                                            # trước đây: IntegrityError lặp lại mãi
    assert d.one("SELECT COUNT(*) n FROM deck_categories")["n"] == 0
    assert d.one("SELECT category_id FROM decks WHERE id=?", (deck,))["category_id"] is None
    d.sync()
    assert remote(cloud, "decks")[0]["description"] == "sửa dở"


def test_soft_deleted_deck_name_can_be_reused_and_legacy_db_migrates(tmp_path):
    p = str(tmp_path / "old.db")
    c = sqlite3.connect(p)
    c.executescript("""create table decks(id text primary key,name text not null unique,description text,color text,icon text,category_id text,
        created_at datetime not null default (datetime('now','localtime')),updated_at datetime,deleted_at datetime);
        create table deck_cards(id text primary key,deck_id text not null references decks(id) on delete cascade,card_id text not null,
        added_at datetime,updated_at datetime,deleted_at datetime,unique(deck_id,card_id));
        create table radicals(id text primary key,character text not null unique,name text,color text,sort_order integer default 0,
        created_at datetime default (datetime('now','localtime')),updated_at datetime,deleted_at datetime);
        insert into decks(id,name) values('d1','A'); insert into deck_cards(id,deck_id,card_id) values('l1','d1','c1');
        insert into radicals(id,character) values('r1','木');""")
    c.commit(); c.close()
    db_module.init_db(db_path=p)
    c = sqlite3.connect(p)
    assert c.execute("SELECT COUNT(*) FROM deck_cards").fetchone()[0] == 1          # DROP TABLE không kéo theo CASCADE
    c.execute("UPDATE decks SET deleted_at=datetime('now') WHERE id='d1'")
    c.execute("INSERT INTO decks(id,name) VALUES('d2','A')")                        # tạo lại cùng tên: được
    c.execute("UPDATE radicals SET deleted_at=datetime('now') WHERE id='r1'")
    c.execute("INSERT INTO radicals(id,character) VALUES('r2','木')")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO decks(id,name) VALUES('d3','A')")                    # hai bộ CHƯA xoá cùng tên: vẫn cấm
    c.close()
    db_module.init_db(db_path=p)                                                     # chạy lại: idempotent


def test_sync_is_serialised_and_has_deadline(mk, cloud):
    d = mk()
    add_card(d)
    assert cloud_sync._SYNC_LOCK.acquire(blocking=False)
    try:
        ok, _, err = d.sync(expect_ok=False)
        assert not ok and "đồng bộ khác" in err
    finally:
        cloud_sync._SYNC_LOCK.release()
    _common.close_thread_connection()
    auth = StaticAuth(pg_harness.jwt(d.uid), d.uid)
    ok, _, err = CloudSync(auth=auth, rest_url=cloud.rest_url, db_path=d.path, deadline_s=1e-9).sync()
    assert not ok and "Quá thời gian" in err
    d.sync()                                                                          # lần sau vẫn chạy bình thường


def test_stored_sig_not_set_after_push(mk, cloud):
    d = mk()
    add_card(d)
    d.sync()
    assert d.one("SELECT value FROM _sync_state WHERE key='sig'")["value"] == ""   # đã đẩy → buộc kiểm tra lại lần sau
    d.sync()
    assert d.one("SELECT value FROM _sync_state WHERE key='sig'")["value"] != ""   # không đẩy gì → nhớ chữ ký


def test_settings_write_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings_module, "_cache", {})
    settings_module.set("cloud_refresh_token", "abc")
    assert os.path.exists(tmp_path / "s.json") and not os.path.exists(tmp_path / "s.json.tmp")
    monkeypatch.setattr(settings_module, "_cache", {})
    assert settings_module.get("cloud_refresh_token") == "abc"


def test_bulk_favorite_is_uniform(fresh_db):
    a = models.add_card(card_payload(character="猫", is_favorite=1))
    b = models.add_card(card_payload(character="犬", is_favorite=0))
    models.bulk_toggle_favorite([a, b])
    assert [models.get_card_by_id(i)["is_favorite"] for i in (a, b)] == [1, 1]
    models.bulk_toggle_favorite([a, b])
    assert [models.get_card_by_id(i)["is_favorite"] for i in (a, b)] == [0, 0]
