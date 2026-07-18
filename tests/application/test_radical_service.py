from application.radical_service import RadicalService
from application.card_service import CardService
from infrastructure.db.sqlite_repositories import SqliteRadicalRepository, SqliteCardRepository
from tests.conftest import card_payload
import pytest


@pytest.fixture
def service(fresh_db):
    return RadicalService(SqliteRadicalRepository())


def test_add_update_delete(service):
    radical_id = service.add("日", name="bộ Nhật (mặt trời)", color="#000000")
    radical = next(r for r in service.list_radicals() if r["id"] == radical_id)
    assert radical["character"] == "日"
    assert radical["name"] == "bộ Nhật (mặt trời)"

    service.update(radical_id, "水", "bộ Thủy (nước)", "#111111")
    radical = next(r for r in service.list_radicals() if r["id"] == radical_id)
    assert radical["character"] == "水"
    assert radical["name"] == "bộ Thủy (nước)"

    service.delete(radical_id)
    assert radical_id not in [r["id"] for r in service.list_radicals()]


def test_new_radical_starts_with_no_cards(service):
    radical_id = service.add("日")
    radical = next(r for r in service.list_radicals() if r["id"] == radical_id)
    assert radical["card_count"] == 0


def test_assign_and_lookup_cards_for_a_radical(service, fresh_db):
    # "tra cứu 1 bộ gồm nhiều từ thuộc bộ đó"
    card_service = CardService(SqliteCardRepository())
    radical_id = service.add("日", name="bộ Nhật")
    c1 = card_service.add(card_payload(character="暗", type="kanji"))
    c2 = card_service.add(card_payload(character="明", type="kanji"))
    c3 = card_service.add(card_payload(character="猫", type="vocab"))  # not assigned

    service.add_card(radical_id, c1)
    service.add_card(radical_id, c2)

    cards = service.get_cards_for_radical(radical_id)
    assert {c["id"] for c in cards} == {c1, c2}
    assert c3 not in {c["id"] for c in cards}


def test_get_radicals_for_card_and_remove(service, fresh_db):
    card_service = CardService(SqliteCardRepository())
    radical_id = service.add("日")
    card_id = card_service.add(card_payload(character="暗", type="kanji"))

    assert service.get_radicals_for_card(card_id) == []
    service.add_card(radical_id, card_id)
    radicals = service.get_radicals_for_card(card_id)
    assert [r["id"] for r in radicals] == [radical_id]

    service.remove_card(radical_id, card_id)
    assert service.get_radicals_for_card(card_id) == []


def test_a_card_can_belong_to_several_radicals(service, fresh_db):
    card_service = CardService(SqliteCardRepository())
    r1 = service.add("日")
    r2 = service.add("音")
    card_id = card_service.add(card_payload(character="暗", type="kanji"))

    service.add_card(r1, card_id)
    service.add_card(r2, card_id)

    radical_ids = {r["id"] for r in service.get_radicals_for_card(card_id)}
    assert radical_ids == {r1, r2}


def test_reorder_persists_new_order(service):
    a = service.add("日")
    b = service.add("水")
    c = service.add("火")

    service.reorder([c, a, b])
    ordered_ids = [r["id"] for r in service.list_radicals()]
    assert ordered_ids == [c, a, b]
