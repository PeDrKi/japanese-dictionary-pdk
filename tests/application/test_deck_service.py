from application.deck_service import DeckService
from application.card_service import CardService
from infrastructure.db.sqlite_repositories import SqliteDeckRepository, SqliteCardRepository
from tests.conftest import card_payload
import pytest


@pytest.fixture
def service(fresh_db):
    return DeckService(SqliteDeckRepository())


def test_add_update_delete(service):
    deck_id = service.add("Bộ thẻ test", description="mô tả", color="#000000", icon="📚")
    deck = next(d for d in service.list_decks() if d["id"] == deck_id)
    assert deck["name"] == "Bộ thẻ test"

    service.update(deck_id, "Đổi tên", "mô tả mới", "#111111", "🔥")
    deck = next(d for d in service.list_decks() if d["id"] == deck_id)
    assert deck["name"] == "Đổi tên"

    service.delete(deck_id)
    assert deck_id not in [d["id"] for d in service.list_decks()]


def test_add_card_and_bulk_add_cards(service, fresh_db):
    card_service = CardService(SqliteCardRepository())
    deck_id = service.add("Bộ thẻ test")
    c1 = card_service.add(card_payload(character="猫"))
    c2 = card_service.add(card_payload(character="鳥"))

    service.add_card(deck_id, c1)
    service.bulk_add_cards(deck_id, [c1, c2])

    ids_in_deck = [c["id"] for c in card_service.list_cards(deck_id=deck_id)]
    assert set(ids_in_deck) == {c1, c2}


def test_categories(service):
    cat_id = service.add_category("Sách Kanji", icon="📘")
    assert any(c["id"] == cat_id for c in service.list_categories())

    service.update_category(cat_id, "Sách Kanji tập 1", "📗")
    cat = next(c for c in service.list_categories() if c["id"] == cat_id)
    assert cat["name"] == "Sách Kanji tập 1"

    service.delete_category(cat_id)
    assert cat_id not in [c["id"] for c in service.list_categories()]


def test_get_decks_for_card(service, fresh_db):
    card_service = CardService(SqliteCardRepository())
    deck_id = service.add("Bộ thẻ test")
    card_id = card_service.add(card_payload(character="嵐"))

    assert service.get_decks_for_card(card_id) == []
    service.add_card(deck_id, card_id)
    decks = service.get_decks_for_card(card_id)
    assert [d["id"] for d in decks] == [deck_id]


def test_remove_card(service, fresh_db):
    card_service = CardService(SqliteCardRepository())
    deck_id = service.add("Bộ thẻ test")
    card_id = card_service.add(card_payload(character="嵐"))

    service.add_card(deck_id, card_id)
    assert service.get_decks_for_card(card_id) != []

    service.remove_card(deck_id, card_id)
    assert service.get_decks_for_card(card_id) == []
