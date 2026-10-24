"""
Test tích hợp đồng bộ đám mây: engine thật (infrastructure/cloud_sync.py) ↔ Postgres + PostgREST thật chạy
CÙNG schema.sql với bản web. Mỗi "thiết bị" là 1 file SQLite riêng.
"""
import json
import sqlite3
import time

import pytest

from database import _common
from database import db as db_module
from database import models
from domain.srs import compute_srs_update, next_count, status_from_count
from infrastructure.cloud_sync import (CloudSync, StaticAuth, local_to_utc, utc_to_local, diff_fields, plan_merge)
from tests import pg_harness
from tests.conftest import card_payload

UID = pg_harness.USERS["a"]


class Device:
    def __init__(self, tmp_path, name, monkeypatch, cloud, user="a"):
        self.path = str(tmp_path / f"{name}.db")
        self.mp, self.cloud = monkeypatch, cloud
        self.uid = pg_harness.USERS[user]
        db_module.init_db(db_path=self.path)

    def use(self):
        _common.close_thread_connection()
        self.mp.setattr(db_module, "DB_PATH", self.path)
        return self

    def sync(self, expect_ok=True):
        _common.close_thread_connection()
        auth = StaticAuth(pg_harness.jwt(self.uid), self.uid)
        ok, stats, err = CloudSync(auth=auth, rest_url=self.cloud.rest_url, db_path=self.path).sync()
        if expect_ok:
            assert ok, err
        self.last = stats
        if expect_ok:
            assert not stats["errors"], stats["errors"]
        return ok, stats, err

    def q(self, sql, args=()):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()

    def one(self, sql, args=()):
        r = self.q(sql, args)
        return r[0] if r else None

    def sql(self, sql, args=()):
        c = sqlite3.connect(self.path)
        c.execute(sql, args)
        c.commit()
        c.close()


@pytest.fixture
def mk(tmp_path, monkeypatch, cloud):
    def make(name="d1", user="a"):
        return Device(tmp_path, name, monkeypatch, cloud, user)
    return make


def remote(cloud, table, query="", user="a"):
    return cloud.api("GET", f"/{table}?select=*{query}", user=user)


def add_card(dev, **kw):
    dev.use()
    return models.add_card(card_payload(**kw))


# ── tiện ích thuần ───────────────────────────────────────────────────────────

def test_time_roundtrip_and_naive_is_local():
    s = "2026-03-04 15:30:10"
    assert utc_to_local(local_to_utc(s)) == s
    assert local_to_utc(None) is None and utc_to_local(None) is None
    assert utc_to_local("2026-03-04T08:30:10.123456+00:00") == utc_to_local("2026-03-04T08:30:10.123Z")


def test_plan_merge_matches_web_rules():
    base = {"a": 1, "b": 1, "c": 1}
    apply, conflicts = plan_merge(base, {"a": 2, "b": 3, "c": 4}, {"a": 1, "b": 9, "c": 4})
    assert apply == {"a": 2} and [c[0] for c in conflicts] == ["b"]      # c: người kia đã sửa đúng giá trị đó
    assert diff_fields({"x": None}, {"x": ""}, ["x"]) == {}               # None ≡ ''


# ── khởi tạo / đẩy lần đầu ───────────────────────────────────────────────────

def test_first_sync_pushes_everything_and_marks_clean(mk, cloud):
    d = mk()
    d.use()
    cid = models.add_card(card_payload(character="猫", meaning_vi="mèo", status="known"))
    d.sql("UPDATE cards SET srs_interval=30, srs_ease=2.8, srs_due_date='2030-01-01' WHERE id=?", (cid,))
    cat = models.add_category("N5")
    deck = models.add_deck("HSK", "mô tả", category_id=cat)
    models.add_card_to_deck(deck, cid)
    models.log_study(cid, "correct")   # → dirty=1 (RPC) — nhưng thẻ mới nên cần thẻ lên trước
    d.sync()
    r = remote(cloud, "cards")
    assert len(r) == 1 and r[0]["character"] == "猫" and r[0]["version"] >= 1
    assert len(remote(cloud, "decks")) == 1
    assert len(remote(cloud, "deck_cards")) == 1
    assert len(remote(cloud, "study_sessions")) == 1
    assert remote(cloud, "decks")[0]["category_id"] == cat
    assert remote(cloud, "deck_categories")[0]["name"] == "N5"
    assert d.one("SELECT COUNT(*) n FROM cards WHERE dirty=1")["n"] == 0
    assert d.one("SELECT COUNT(*) n FROM study_sessions WHERE dirty!=0")["n"] == 0
    # SRS cục bộ == SRS trên máy chủ
    loc = d.one("SELECT srs_interval, srs_ease, srs_due_date, status FROM cards")
    assert (r[0]["srs_interval"], r[0]["status"]) != (None, None)
    r2 = remote(cloud, "cards")[0]
    assert loc["srs_interval"] == r2["srs_interval"] and loc["status"] == r2["status"]


def test_history_sessions_do_not_change_remote_srs(mk, cloud):
    d = mk()
    d.use()
    cid = models.add_card(card_payload(character="犬", meaning_vi="chó"))
    d.sql("UPDATE cards SET srs_interval=20, srs_ease=2.0, srs_due_date='2031-02-02', status='known' WHERE id=?", (cid,))
    for _ in range(3):
        d.sql("INSERT INTO study_sessions (id,card_id,result,studied_at,dirty) VALUES (lower(hex(randomblob(16))),?,'correct',datetime('now','localtime','-3 day'),2)", (cid,))
    d.sync()
    c = remote(cloud, "cards")[0]
    assert (c["srs_interval"], c["srs_ease"], c["srs_due_date"]) == (20, 2.0, "2031-02-02")
    assert len(remote(cloud, "study_sessions")) == 3


def test_second_sync_is_noop(mk, cloud):
    d = mk()
    add_card(d)
    d.sync()
    n = remote(cloud, "cards")[0]["version"]
    ok, stats, _ = d.sync()
    assert remote(cloud, "cards")[0]["version"] == n
    assert stats["pushed"] == 0 and stats["pulled"] == 0


def test_offline_failure_keeps_local_changes_dirty(mk, cloud):
    d = mk()
    add_card(d)
    auth = StaticAuth(pg_harness.jwt(d.uid), d.uid)
    ok, _, err = CloudSync(auth=auth, rest_url="http://127.0.0.1:9", db_path=d.path, timeout=2).sync()
    assert not ok and err
    assert d.one("SELECT COUNT(*) n FROM cards WHERE dirty=1")["n"] == 1
    d.sync()
    assert len(remote(cloud, "cards")) == 1


# ── kéo từ máy chủ (thiết bị khác / web) ─────────────────────────────────────

def test_pull_cards_created_elsewhere(mk, cloud):
    d = mk()
    cloud.api("POST", "/cards", {"type": "vocab", "character": "水", "meaning_vi": "nước", "is_favorite": True}, "a")
    d.sync()
    r = d.one("SELECT * FROM cards")
    assert r["character"] == "水" and r["is_favorite"] == 1 and r["dirty"] == 0 and r["server_version"] == 1
    assert len(r["id"]) == 36


def test_two_devices_see_each_other(mk, cloud):
    a, b = mk("a"), mk("b")
    ida = add_card(a, character="猫", meaning_vi="mèo")
    a.sync(); b.sync()
    assert b.one("SELECT character FROM cards WHERE id=?", (ida,))["character"] == "猫"
    idb = add_card(b, character="犬", meaning_vi="chó")
    b.sync(); a.sync()
    assert a.one("SELECT character FROM cards WHERE id=?", (idb,))["character"] == "犬"


# ── sửa & gộp ───────────────────────────────────────────────────────────────

def test_edit_pushes_only_changed_fields(mk, cloud):
    d = mk()
    cid = add_card(d)
    d.sync()
    cloud.api("PATCH", f"/cards?id=eq.{cid}", {"notes": "ghi chú từ web"}, "a")      # người khác sửa trường khác
    d.use()
    payload = card_payload(); payload["meaning_vi"] = "sửa ở desktop"
    models.update_card(cid, payload)
    d.sync()
    r = remote(cloud, "cards")[0]
    assert r["meaning_vi"] == "sửa ở desktop" and r["notes"] == "ghi chú từ web"       # không ghi đè notes
    assert d.one("SELECT notes, dirty FROM cards")["notes"] == "ghi chú từ web"
    assert d.one("SELECT dirty FROM cards")["dirty"] == 0


def test_same_field_conflict_newer_wins_and_is_logged(mk, cloud):
    d = mk()
    cid = add_card(d)
    d.sync()
    d.use()
    p = card_payload(); p["meaning_en"] = "LOCAL"
    models.update_card(cid, p)                                                          # sửa cục bộ (mới nhất sau cùng)
    time.sleep(1.2)
    cloud.api("PATCH", f"/cards?id=eq.{cid}", {"meaning_en": "REMOTE"}, "a")            # máy chủ mới hơn
    ok, stats, _ = d.sync()
    assert remote(cloud, "cards")[0]["meaning_en"] == "REMOTE"
    assert d.one("SELECT meaning_en FROM cards")["meaning_en"] == "REMOTE"
    assert len(stats["conflicts"]) == 1 and "LOCAL" in stats["conflicts"][0]
    log = d.one("SELECT * FROM sync_conflicts")
    assert log["field"] == "meaning_en" and log["local_value"] == "LOCAL" and log["kept"] == "máy chủ"


def test_same_field_conflict_local_newer_wins(mk, cloud):
    d = mk()
    cid = add_card(d)
    d.sync()
    cloud.api("PATCH", f"/cards?id=eq.{cid}", {"meaning_en": "REMOTE"}, "a")
    time.sleep(1.2)
    d.use()
    p = card_payload(); p["meaning_en"] = "LOCAL"
    models.update_card(cid, p)
    d.sync()
    assert remote(cloud, "cards")[0]["meaning_en"] == "LOCAL"


# ── ôn tập ──────────────────────────────────────────────────────────────────

def test_review_matches_desktop_srs_and_is_server_authoritative(mk, cloud):
    d = mk()
    cid = add_card(d)
    d.sync()
    d.use()
    iv, ez, n = 1, 2.5, 0                                  # thẻ mới: 0 lần học
    for res in ("correct", "correct", "incorrect", "correct"):
        models.log_study(cid, res)
        iv, ez = compute_srs_update(iv, ez, res)
        n = next_count(n, res)
    st = status_from_count(n)
    d.sync()
    r = remote(cloud, "cards")[0]
    assert (r["srs_interval"], round(r["srs_ease"], 6), r["status"]) == (iv, round(ez, 6), st)
    loc = d.one("SELECT srs_interval, srs_ease, status, dirty FROM cards")
    assert (loc["srs_interval"], round(loc["srs_ease"], 6), loc["status"], loc["dirty"]) == (iv, round(ez, 6), st, 0)
    assert len(remote(cloud, "study_sessions")) == 4
    assert r["study_count"] == n == d.one("SELECT study_count FROM cards")["study_count"]


def test_two_devices_reviewing_same_card_both_count(mk, cloud):
    a, b = mk("a"), mk("b")
    cid = add_card(a)
    a.sync(); b.sync()
    a.use(); models.log_study(cid, "correct")
    time.sleep(0.01)
    b.use(); models.log_study(cid, "correct")
    a.sync(); b.sync(); a.sync()
    assert len(remote(cloud, "study_sessions")) == 2
    r = remote(cloud, "cards")[0]
    iv, ez = compute_srs_update(*compute_srs_update(1, 2.5, "correct"), "correct")[:1] + (0,), 0   # noqa
    # lần 2 chạy trên kết quả lần 1 (server nối tiếp 2 lượt)
    i1, e1 = compute_srs_update(1, 2.5, "correct")
    i2, e2 = compute_srs_update(i1, e1, "correct")
    assert (r["srs_interval"], round(r["srs_ease"], 6)) == (i2, round(e2, 6))
    for dev in (a, b):
        assert dev.one("SELECT srs_interval FROM cards")["srs_interval"] == i2


def test_edit_form_never_overwrites_srs_progress(mk, cloud):
    a, b = mk("a"), mk("b")
    cid = add_card(a)
    a.sync(); b.sync()
    b.use(); models.log_study(cid, "correct"); b.sync()          # b ôn → SRS đổi trên máy chủ
    a.use(); p = card_payload(); p["notes"] = "sửa tay"; models.update_card(cid, p)
    a.sync()                                                    # a sửa ghi chú (không biết SRS mới)
    r = remote(cloud, "cards")[0]
    assert r["notes"] == "sửa tay" and r["srs_interval"] > 1 and r["status"] == "learning"


# ── xóa ─────────────────────────────────────────────────────────────────────

def test_soft_delete_and_restore_propagate(mk, cloud):
    a, b = mk("a"), mk("b")
    cid = add_card(a)
    a.sync(); b.sync()
    a.use(); models.soft_delete_card(cid); a.sync(); b.sync()
    assert remote(cloud, "cards")[0]["deleted_at"] is not None
    assert b.one("SELECT deleted_at FROM cards")["deleted_at"] is not None
    b.use(); models.restore_card(cid); b.sync(); a.sync()
    assert remote(cloud, "cards")[0]["deleted_at"] is None
    assert a.one("SELECT deleted_at FROM cards")["deleted_at"] is None


def test_hard_delete_propagates_both_ways(mk, cloud):
    a, b = mk("a"), mk("b")
    c1, c2 = add_card(a, character="一", meaning_vi="1"), add_card(a, character="二", meaning_vi="2")
    a.sync(); b.sync()
    a.use(); models.hard_delete_card(c1); a.sync()
    assert [r["id"] for r in remote(cloud, "cards")] == [c2]
    b.sync()
    assert [r["id"] for r in b.q("SELECT id FROM cards")] == [c2]
    cloud.api("DELETE", f"/cards?id=eq.{c2}", None, "a")             # xóa trực tiếp ở máy chủ (vd. từ web)
    a.sync()
    assert a.q("SELECT id FROM cards") == []


def test_edit_after_remote_hard_delete_recreates(mk, cloud):
    d = mk()
    cid = add_card(d)
    d.sync()
    cloud.api("DELETE", f"/cards?id=eq.{cid}", None, "a")
    d.use(); p = card_payload(); p["notes"] = "còn sửa dở"; models.update_card(cid, p)
    d.sync()
    r = remote(cloud, "cards")
    assert len(r) == 1 and r[0]["notes"] == "còn sửa dở"


# ── bộ thẻ / danh mục / liên kết ─────────────────────────────────────────────

def test_same_deck_name_created_on_two_devices_is_unified(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use(); da = models.add_deck("HSK"); ca = models.add_card(card_payload(character="一", meaning_vi="1")); models.add_card_to_deck(da, ca)
    b.use(); db_ = models.add_deck("HSK"); cb = models.add_card(card_payload(character="二", meaning_vi="2")); models.add_card_to_deck(db_, cb)
    a.sync(); b.sync(); a.sync()
    assert len(remote(cloud, "decks")) == 1
    assert len(a.q("SELECT id FROM decks")) == 1 and len(b.q("SELECT id FROM decks")) == 1
    assert a.q("SELECT id FROM decks") == b.q("SELECT id FROM decks")
    assert len(remote(cloud, "deck_cards")) == 2
    assert len(a.q("SELECT * FROM deck_cards WHERE deleted_at IS NULL")) == 2
    assert not a.last["errors"] and not b.last["errors"]


def test_deck_link_remove_and_readd_syncs(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use(); deck = models.add_deck("D"); cid = models.add_card(card_payload()); models.add_card_to_deck(deck, cid)
    a.sync(); b.sync()
    a.use(); models.remove_card_from_deck(deck, cid); a.sync(); b.sync()
    assert b.one("SELECT deleted_at FROM deck_cards")["deleted_at"] is not None
    b.use(); models.add_card_to_deck(deck, cid); b.sync(); a.sync()
    assert a.one("SELECT deleted_at FROM deck_cards")["deleted_at"] is None
    assert remote(cloud, "deck_cards")[0]["deleted_at"] is None


def test_deck_rename_on_two_devices_merges_other_fields(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use(); deck = models.add_deck("Gốc", "mô tả", "#111111", "📁")
    a.sync(); b.sync()
    a.use(); models.update_deck(deck, "Gốc", "mô tả mới", "#111111", "📁")
    b.use(); models.update_deck(deck, "Gốc", "mô tả", "#222222", "📁")
    a.sync(); b.sync(); a.sync()
    r = remote(cloud, "decks")[0]
    assert r["description"] == "mô tả mới" and r["color"] == "#222222"


def test_radicals_and_decompositions_sync(mk, cloud):
    from database import _radicals, _user_decompositions  # noqa
    a, b = mk("a"), mk("b")
    a.use()
    rid = models.add_radical("氵", "thủy")
    cid = models.add_card(card_payload(character="海", meaning_vi="biển"))
    models.add_card_to_radical(rid, cid)
    models.set_user_decomposition("海", "氵毎")
    a.sync(); b.sync()
    assert b.one("SELECT character FROM radicals")["character"] == "氵"
    assert len(b.q("SELECT * FROM radical_cards WHERE deleted_at IS NULL")) == 1
    assert remote(cloud, "user_decompositions")[0]["parts"] == "氵毎"
    assert b.one("SELECT parts FROM user_decompositions WHERE character='海'")["parts"] == "氵毎"
    # đổi bộ + gỡ liên kết ở b → sang a
    b.use(); models.set_user_decomposition("海", "水毎"); b.sync(); a.sync()
    assert a.one("SELECT parts FROM user_decompositions WHERE character='海'")["parts"] == "水毎"


# ── cô lập người dùng, danh mục, bộ thủ, phiên từ web ────────────────────────

def test_users_are_isolated(mk, cloud):
    a, b = mk("a", "a"), mk("b", "b")
    add_card(a, character="秘", meaning_vi="bí mật")
    a.sync(); b.sync()
    assert b.q("SELECT * FROM cards") == []
    assert len(remote(cloud, "cards", user="b")) == 0


def test_category_unified_by_name_and_rename_propagates(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use(); ca = models.add_category("N5")
    b.use(); cb = models.add_category("N5")
    a.sync(); b.sync(); a.sync()
    assert len(remote(cloud, "deck_categories")) == 1
    assert a.q("SELECT id FROM deck_categories") == b.q("SELECT id FROM deck_categories")
    cid = a.one("SELECT id FROM deck_categories")["id"]
    a.sql("UPDATE deck_categories SET icon='🌸' WHERE id=?", (cid,))
    a.sync(); b.sync()
    assert b.one("SELECT icon FROM deck_categories")["icon"] == "🌸"


def test_radical_same_character_on_two_devices_is_unified(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use(); models.add_radical("火", "hỏa")
    b.use(); models.add_radical("火", "lửa")
    a.sync(); b.sync(); a.sync()
    assert len(remote(cloud, "radicals")) == 1
    assert a.q("SELECT id FROM radicals") == b.q("SELECT id FROM radicals")
    assert not a.last["errors"] and not b.last["errors"]


def test_study_history_from_other_device_is_pulled(mk, cloud):
    a, b = mk("a"), mk("b")
    cid = add_card(a)
    a.sync(); b.sync()
    a.use(); models.log_study(cid, "correct"); models.log_study(cid, "incorrect"); a.sync(); b.sync()
    assert b.one("SELECT COUNT(*) n FROM study_sessions")["n"] == 2
    assert b.one("SELECT COUNT(*) n FROM study_sessions WHERE dirty!=0")["n"] == 0


def test_local_edit_of_card_trashed_remotely_keeps_it_in_trash_with_merged_fields(mk, cloud):
    d = mk()
    cid = add_card(d)
    d.sync()
    cloud.api("PATCH", f"/cards?id=eq.{cid}", {"deleted_at": "2026-01-01T00:00:00+00:00"}, "a")
    d.use(); p = card_payload(); p["notes"] = "sửa sau khi bị xóa"; models.update_card(cid, p)
    d.sync()
    r = remote(cloud, "cards")[0]
    assert r["deleted_at"] is not None and r["notes"] == "sửa sau khi bị xóa"


def test_timezone_independent(mk, cloud, monkeypatch):
    """Cùng thời điểm thật, máy ở múi giờ khác nhau → cùng giá trị UTC trên máy chủ."""
    import os
    d = mk()
    cid = add_card(d)
    d.sql("UPDATE cards SET created_at='2026-06-01 12:00:00' WHERE id=?", (cid,))
    monkeypatch.setenv("TZ", "Asia/Ho_Chi_Minh"); time.tzset()
    try:
        d.sync()
    finally:
        monkeypatch.delenv("TZ"); time.tzset()
    assert remote(cloud, "cards")[0]["created_at"].startswith("2026-06-01T05:00:00")
