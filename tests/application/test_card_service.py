"""
Tests for application/card_service.py.

Wired against the real SQLite repositories (fresh_db fixture) rather
than a fake, since no fake exists yet — this also incidentally verifies
the whole chain (service → repository → database) works end to end, not
just the service in isolation.
"""
import pytest

from application.card_service import CardService
from infrastructure.db.sqlite_repositories import SqliteCardRepository
from tests.conftest import card_payload


@pytest.fixture
def service(fresh_db):
    return CardService(SqliteCardRepository())


# ── validate_and_build: mirrors ui/card_form.py's _save() pre-processing ──

def test_validate_and_build_success(service):
    data, check = service.validate_and_build(
        card_type="vocab", character="  食べる  ", meaning_vi="  ăn  ",
        meaning_en="eat",
    )
    assert check == {"character": True, "meaning_vi": True, "valid": True}
    # stripped, and shaped the same way domain.validators.build_card_data does
    assert data["character"] == "食べる"
    assert data["meaning_vi"] == "ăn"
    assert data["meaning_en"] == "eat"
    assert data["type"] == "vocab"


def test_validate_and_build_missing_character(service):
    data, check = service.validate_and_build(
        card_type="vocab", character="   ", meaning_vi="ăn"
    )
    assert data is None
    assert check == {"character": False, "meaning_vi": True, "valid": False}


def test_validate_and_build_missing_meaning(service):
    data, check = service.validate_and_build(
        card_type="vocab", character="猫", meaning_vi=""
    )
    assert data is None
    assert check == {"character": True, "meaning_vi": False, "valid": False}


def test_validate_and_build_truncates_before_shaping(service):
    from constants import MAX_CHARACTER_LEN
    too_long = "あ" * (MAX_CHARACTER_LEN + 50)
    data, check = service.validate_and_build(
        card_type="hiragana", character=too_long, meaning_vi="x"
    )
    assert check["valid"] is True
    assert len(data["character"]) == MAX_CHARACTER_LEN


def test_validate_and_build_then_add_round_trip(service):
    data, check = service.validate_and_build(
        card_type="kanji", character="雨", meaning_vi="mưa",
        reading_kun="あめ",
    )
    assert check["valid"] is True
    card_id = service.add(data)
    stored = service.get(card_id)
    assert stored["character"] == "雨"
    assert stored["reading_kun"] == "あめ"


# ── Queries ────────────────────────────────────────────────────────────────

def test_list_cards_forwards_filters(service):
    service.add(card_payload(character="猫", type="vocab"))
    result = service.list_cards(type_filter="vocab")
    assert all(c["type"] == "vocab" for c in result)


def test_count_matches_list_length(service):
    service.add(card_payload(character="猫"))
    assert service.count() == len(service.list_cards())


def test_due_count(service):
    assert service.due_count() >= 0


def test_get_deleted_empty_initially_for_new_card(service):
    card_id = service.add(card_payload(character="猫"))
    assert card_id not in [c["id"] for c in service.get_deleted()]


def test_check_duplicates(service):
    card_id = service.add(card_payload(character="犬", type="vocab"))
    assert len(service.check_duplicates("犬", "vocab")) == 1
    assert service.check_duplicates("犬", "vocab", exclude_id=card_id) == []


# ── Commands ─────────────────────────────────────────────────────────────

def test_update(service):
    card_id = service.add(card_payload())
    service.update(card_id, card_payload(character="犬", meaning_vi="đổi rồi"))
    assert service.get(card_id)["meaning_vi"] == "đổi rồi"


def test_soft_delete_restore_hard_delete(service):
    card_id = service.add(card_payload())
    service.soft_delete(card_id)
    assert card_id not in [c["id"] for c in service.list_cards()]
    service.restore(card_id)
    assert card_id in [c["id"] for c in service.list_cards()]
    service.hard_delete(card_id)
    assert service.get(card_id) is None


def test_toggle_favorite(service):
    card_id = service.add(card_payload(is_favorite=0))
    service.toggle_favorite(card_id)
    assert service.get(card_id)["is_favorite"] == 1


def test_bulk_operations(service):
    ids = [service.add(card_payload(character=c)) for c in "猫鳥魚"]
    service.bulk_update_status(ids, "known")
    assert all(service.get(i)["status"] == "known" for i in ids)
    service.bulk_toggle_favorite(ids)
    assert all(service.get(i)["is_favorite"] == 1 for i in ids)
    snapshots = service.bulk_soft_delete(ids)
    assert {s["id"] for s in snapshots} == set(ids)
