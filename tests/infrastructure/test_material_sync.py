"""Đồng bộ Ngữ pháp / Bản dịch / Chia động từ giữa desktop ↔ Postgres (cùng schema bản web) ↔ thiết bị khác."""
from application.material_service import MaterialService
from infrastructure.db.sqlite_repositories import SqliteMaterialRepository
from tests.infrastructure.test_cloud_sync import mk, remote   # noqa: F401  (fixture mk + helper)


def svc():
    return MaterialService(SqliteMaterialRepository())


def test_grammar_and_translation_roundtrip_between_devices(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use()
    gid, _ = svc().save_grammar(None, {"title": "〜てから", "meaning_vi": "sau khi", "examples": "食べてから行く。 | Ăn rồi đi.", "jlpt_level": "N4"})
    tid, _ = svc().save_translation(None, {"title": "日記", "jp": "今日は雨です。", "vi": "Hôm nay mưa.", "glossary": "雨 = mưa"})
    a.sync()
    g, t = remote(cloud, "grammar_points")[0], remote(cloud, "translations")[0]
    assert g["title"] == "〜てから" and g["jlpt_level"] == "N4" and t["glossary"] == "雨 = mưa" and t["jp"] == "今日は雨です。"
    b.sync(); b.use()
    assert svc().get_grammar(gid)["examples"].startswith("食べてから") and svc().get_translation(tid)["glossary"] == "雨 = mưa"
    # b sửa, a nhận
    svc().set_glossary_term(tid, None, "今日", "hôm nay")
    b.sync(); a.sync(); a.use()
    assert svc().get_translation(tid)["glossary"] == "雨 = mưa\n今日 = hôm nay"
    assert a.one("SELECT dirty FROM translations")["dirty"] == 0


def test_translation_fields_merge_across_devices(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use()
    tid, _ = svc().save_translation(None, {"title": "T", "jp": "A", "vi": "a"})
    a.sync(); b.sync()
    a.use(); svc()._r.update_translation(tid, {"vi": "a2"})
    b.use(); svc()._r.update_translation(tid, {"glossary": "A = x"})
    a.sync(); b.sync(); a.sync()
    r = remote(cloud, "translations")[0]
    assert (r["vi"], r["glossary"]) == ("a2", "A = x")
    assert a.one("SELECT vi, glossary FROM translations") == {"vi": "a2", "glossary": "A = x"}


def test_conj_table_syncs_and_cell_delete_propagates(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use()
    s = svc(); s.add_default_forms()
    vid, n = s.save_verb(None, "たべます", "ăn", 2)
    a.sync()
    assert len(remote(cloud, "conj_forms")) == 11 and remote(cloud, "conj_verbs")[0]["grp"] == 2 and len(remote(cloud, "conj_cells")) == n == 11
    b.sync(); b.use()
    forms = {f["kind"]: f["id"] for f in svc().forms()}
    assert svc().cells()[(vid, forms["te"])] == "たべて"
    svc().set_cell(vid, forms["te"], "たべって")
    svc().set_cell(vid, forms["nai"], "")
    svc().toggle_form(forms["ba"], True)
    b.sync(); a.sync(); a.use()
    assert svc().cells()[(vid, forms["te"])] == "たべって" and (vid, forms["nai"]) not in svc().cells()
    assert [f for f in svc().forms() if f["id"] == forms["ba"]][0]["hidden"] == 1
    assert len(remote(cloud, "conj_cells")) == 10


def test_deleting_verb_and_form_cascades_remotely_and_on_other_device(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use()
    s = svc(); s.add_default_forms(); vid, _ = s.save_verb(None, "のみます", "uống", 1)
    a.sync(); b.sync()
    a.use(); forms = {f["kind"]: f["id"] for f in svc().forms()}
    svc().delete_form(forms["te"]); svc().delete_verb(vid)
    a.sync()
    assert remote(cloud, "conj_verbs") == [] and remote(cloud, "conj_cells") == [] and len(remote(cloud, "conj_forms")) == 10
    b.sync(); b.use()
    assert svc().verbs() == [] and svc().cells() == {} and len(svc().forms()) == 10


def test_grammar_hard_delete_propagates(mk, cloud):
    a, b = mk("a"), mk("b")
    a.use(); gid, _ = svc().save_grammar(None, {"title": "x"})
    a.sync(); b.sync()
    a.use(); svc().delete_grammar(gid); a.sync()
    assert remote(cloud, "grammar_points") == []
    b.sync(); b.use()
    assert svc().get_grammar(gid) is None


def test_study_count_syncs_between_devices(mk, cloud):
    from database import models
    from tests.conftest import card_payload
    a, b = mk("a"), mk("b")
    a.use(); cid = models.add_card(card_payload(status="new"))
    a.sync()
    for _ in range(3):
        models.log_study(cid, "correct")
    models.log_study(cid, "incorrect")
    a.sync()
    r = remote(cloud, "cards")[0]
    assert (r["study_count"], r["status"]) == (2, "learning")
    b.sync(); b.use()
    c = models.get_card_by_id(cid)
    assert (c["study_count"], c["status"]) == (2, "learning")
