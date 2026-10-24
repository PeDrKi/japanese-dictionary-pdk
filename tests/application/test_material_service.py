import sqlite3

import pytest

from application.card_service import CardService
from application.deck_service import DeckService
from application.material_service import MaterialService
from infrastructure.db.sqlite_repositories import SqliteCardRepository, SqliteDeckRepository, SqliteMaterialRepository
from database import db as dbmod


@pytest.fixture
def svc(fresh_db):
    return MaterialService(SqliteMaterialRepository(), CardService(SqliteCardRepository()), DeckService(SqliteDeckRepository()))


def test_grammar_crud_and_examples(svc):
    gid, err = svc.save_grammar(None, {"title": "〜てから", "meaning_vi": "sau khi", "jlpt_level": "n4"})
    assert err is None and svc.get_grammar(gid)["jlpt_level"] == "N4"
    assert svc.save_grammar(None, {"title": " "})[1]
    assert svc.add_example(gid, "食べてから行く。 | Ăn rồi đi.") == "ok"
    assert svc.add_example(gid, "食べてから行く。 | khác") == "dup"
    assert svc.get_grammar(gid)["examples"] == "食べてから行く。 | Ăn rồi đi."
    assert [g["id"] for g in svc.list_grammar(search="sau khi")] == [gid]
    assert svc.list_grammar(jlpt="N1") == []
    svc.delete_grammar(gid)
    assert svc.get_grammar(gid) is None


def test_translation_glossary_and_cards(svc):
    tid, _ = svc.save_translation(None, {"title": "日記", "jp": "今日は友達と映画を見に行きました。\n夜は勉強しました。", "vi": "Hôm nay đi xem phim với bạn.\nTối học bài."})
    assert svc.save_translation(None, {"jp": " "})[1]
    svc.set_glossary_term(tid, None, "映画", "phim")
    svc.set_glossary_term(tid, None, "勉強", "học")
    svc.set_glossary_term(tid, None, "楽しい", "")
    svc.set_glossary_term(tid, None, "映画", "bộ phim")                  # trùng → đổi nghĩa
    assert svc.get_translation(tid)["glossary"] == "映画 = bộ phim\n勉強 = học\n楽しい"
    svc.delete_glossary_term(tid, 2)
    p = svc.card_preset(svc.get_translation(tid), "映画", "phim")
    assert p["example_jp"] == "今日は友達と映画を見に行きました。" and p["example_vi"] == "Hôm nay đi xem phim với bạn." and p["source"] == "日記"
    deck = svc._decks.add("Bài 1")
    made, skipped = svc.cards_from_glossary(tid, [0, 1], [deck])
    assert (made, skipped) == (2, 0)
    cards = svc._cards.list_cards(search="映画")
    assert cards[0]["meaning_vi"] == "bộ phim" and cards[0]["status"] == "new"
    assert svc.cards_from_glossary(tid, [0, 1], [deck]) == (0, 2)       # đã có thẻ → bỏ qua


def test_conj_table_fill_and_edit(svc):
    ids = svc.add_default_forms()
    assert len(ids) == 11 and svc.add_default_forms() == []
    vid, n = svc.save_verb(None, "たべます", "ăn", 2)
    assert n == 11
    forms = {f["kind"]: f["id"] for f in svc.forms()}
    cells = svc.cells()
    assert cells[(vid, forms["te"])] == "たべて" and cells[(vid, forms["potential"])] == "たべられる"
    assert svc.set_cell(vid, forms["te"], "たべって") and svc.cells()[(vid, forms["te"])] == "たべって"
    assert svc.fill(verb_ids=[vid]) == 0                                    # không ghi đè ô đã có
    assert svc.fill(verb_ids=[vid], overwrite=True) == 11 and svc.cells()[(vid, forms["te"])] == "たべて"
    assert svc.set_cell(vid, forms["te"], "") and (vid, forms["te"]) not in svc.cells()
    svc.toggle_form(forms["nai"], True)
    assert forms["nai"] not in [f["id"] for f in svc.forms(include_hidden=False)]
    first = svc.forms()[0]["id"]
    svc.move_form(first, 1)
    assert svc.forms()[1]["id"] == first
    svc.delete_form(forms["ta"])
    assert all(k[1] != forms["ta"] for k in svc.cells())                    # xóa cột → xóa ô (cascade)
    svc.delete_verb(vid)
    assert svc.cells() == {}


def test_conj_candidates_from_cards(svc):
    from tests.conftest import card_payload
    svc._cards.add(card_payload(character="飲む", pos="verb1", reading_kana="のむ", meaning_vi="uống"))
    svc._cards.add(card_payload(character="勉強する", pos="verb3", meaning_vi="học"))
    svc._cards.add(card_payload(character="犬", pos="noun"))
    c = svc.candidates()
    assert sorted((x["masu"], x["grp"]) for x in c) == [("勉強します", 3), ("飲みます", 1)]
    svc.add_default_forms()
    assert svc.import_candidates(c) == 2 and svc.candidates() == []


def test_new_tables_are_dirty_and_tombstoned(svc):
    gid, _ = svc.save_grammar(None, {"title": "x"})
    conn = sqlite3.connect(dbmod.DB_PATH)
    assert conn.execute("SELECT dirty FROM grammar_points WHERE id=?", (gid,)).fetchone()[0] == 1
    conn.execute("UPDATE grammar_points SET base_json='{}', dirty=0 WHERE id=?", (gid,)); conn.commit(); conn.close()
    svc.save_grammar(gid, {"title": "y"})
    conn = sqlite3.connect(dbmod.DB_PATH)
    assert conn.execute("SELECT dirty FROM grammar_points WHERE id=?", (gid,)).fetchone()[0] == 1
    conn.execute("UPDATE grammar_points SET base_json='{}' WHERE id=?", (gid,)); conn.commit(); conn.close()
    svc.delete_grammar(gid)
    conn = sqlite3.connect(dbmod.DB_PATH)
    assert conn.execute("SELECT tbl,row_id FROM _sync_tombstones").fetchall() == [("grammar_points", gid)]
