"""Từ loại (pos): validators, lưu DB, lọc, CSV, migration, đồng bộ đám mây."""
import sqlite3

from database import db as db_module, models
from domain.validators import build_card_data, normalize_pos
from infrastructure.csv_handler import import_csv, export_csv
from tests.conftest import card_payload
from tests.infrastructure.test_cloud_sync import Device, mk, remote, add_card  # noqa: F401


def test_normalize_pos_accepts_codes_and_names():
    assert normalize_pos("verb1") == "verb1"
    assert normalize_pos(" Động từ nhóm 2 ") == "verb2"
    assert normalize_pos("godan") == "verb1" and normalize_pos("ichidan") == "verb2"
    assert normalize_pos("Tính từ đuôi い") == "adj_i" and normalize_pos("na-adj") == "adj_na"
    assert normalize_pos("") is None and normalize_pos("bậy") is None and normalize_pos(None) is None


def test_build_card_data_pos_for_every_type():
    base = dict(character="食べる", meaning_vi="ăn")
    assert build_card_data(card_type="vocab", pos="verb2", **base)["pos"] == "verb2"
    assert build_card_data(card_type="kanji", pos="verb2", **base)["pos"] == "verb2"
    assert build_card_data(card_type="vocab", pos="xxx", **base)["pos"] is None


def test_db_save_filter_and_count(fresh_db):
    a = models.add_card(card_payload(character="食べる", pos="verb2"))
    models.add_card(card_payload(character="犬", pos="noun"))
    models.add_card(card_payload(character="高い", pos="adj_i"))
    models.add_card(card_payload(character="水"))                         # không có pos
    assert [c["character"] for c in models.get_all_cards(pos_filter="verb2")] == ["食べる"]
    assert models.count_cards(pos_filter="noun") == 1
    assert models.get_card_by_id(a)["pos"] == "verb2"
    data = card_payload(character="食べる", pos="verb1")
    models.update_card(a, data)
    assert models.get_card_by_id(a)["pos"] == "verb1"


def test_old_db_without_pos_column_is_upgraded(tmp_path):
    p = str(tmp_path / "o.db")
    db_module.init_db(db_path=p)
    c = sqlite3.connect(p)
    c.execute("ALTER TABLE cards DROP COLUMN pos")
    c.commit(); c.close()
    db_module.init_db(db_path=p)
    c = sqlite3.connect(p)
    assert "pos" in [r[1] for r in c.execute("PRAGMA table_info(cards)")]
    c.close()


def test_csv_roundtrip_with_pos(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("type,character,meaning_vi,pos\nvocab,食べる,ăn,Động từ nhóm 2\nvocab,犬,chó,noun\nkanji,雨,mưa,noun\nvocab,水,nước,bậy\n", encoding="utf-8")
    valid, errors = import_csv(str(f))
    assert not errors
    assert [r["pos"] for r in valid] == ["verb2", "noun", "noun", None]
    out = tmp_path / "o.csv"
    export_csv(valid, str(out))
    assert "pos" in out.read_text(encoding="utf-8-sig").splitlines()[0].split(",")


def test_pos_syncs_and_merges_by_field(mk, cloud):
    d1, d2 = mk("d1"), mk("d2")
    cid = add_card(d1, character="食べる", pos="verb2")
    d1.sync()
    assert remote(cloud, "cards")[0]["pos"] == "verb2"
    d2.sync()
    assert d2.one("SELECT pos FROM cards")["pos"] == "verb2"
    d1.sql("UPDATE cards SET pos='verb1' WHERE id=?", (cid,))           # d1 đổi từ loại
    d2.sql("UPDATE cards SET meaning_en='eat' WHERE id=?", (cid,))      # d2 sửa trường khác
    d1.sync(); d2.sync(); d1.sync()
    r = remote(cloud, "cards")[0]
    assert r["pos"] == "verb1" and r["meaning_en"] == "eat"
    assert d2.one("SELECT pos FROM cards")["pos"] == "verb1"


def test_invalid_local_pos_does_not_break_sync(mk, cloud):
    d = mk()
    cid = add_card(d, character="犬")
    d.sql("UPDATE cards SET pos='rác' WHERE id=?", (cid,))
    d.sync()                                                             # máy chủ có CHECK: phải gửi NULL thay vì bị từ chối
    assert remote(cloud, "cards")[0]["pos"] is None


def test_extended_pos_values_roundtrip_and_sync(mk, cloud):
    from constants import CARD_POS
    assert len(CARD_POS) == 12 and {"pronoun", "particle", "adverb", "conjunction", "interjection", "verb"} <= set(CARD_POS)
    for name, code in {"Đại từ": "pronoun", "trợ từ": "particle", "Trạng từ": "adverb", "liên từ": "conjunction",
                       "Thán từ": "interjection", "Động từ": "verb"}.items():
        assert normalize_pos(name) == code
    d = mk()
    for i, code in enumerate(CARD_POS):
        add_card(d, character=f"字{i}", pos=code)
    d.sync()
    assert {r["pos"] for r in remote(cloud, "cards")} == set(CARD_POS)
