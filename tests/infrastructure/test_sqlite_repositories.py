"""
Tests for infrastructure/db/sqlite_repositories.py.

These classes are pure delegation to database.models (already covered by
tests/test_models.py), so the goal here isn't to re-verify SQL behavior —
it's to catch wiring mistakes in the wrapper itself (wrong param name,
wrong order, wrong default) that tests/test_models.py can't see because
it never goes through this class.
"""
from database import models
from infrastructure.db.sqlite_repositories import (
    SqliteCardRepository,
    SqliteDeckRepository,
    SqliteStudySessionRepository,
)
from tests.conftest import card_payload


# ── CardRepository ───────────────────────────────────────────────────────────

def test_card_repo_add_and_get_by_id(fresh_db):
    repo = SqliteCardRepository()
    card_id = repo.add(card_payload(character="猫", meaning_vi="con mèo"))
    card = repo.get_by_id(card_id)
    assert card["character"] == "猫"
    assert card["meaning_vi"] == "con mèo"


def test_card_repo_get_all_matches_models(fresh_db):
    repo = SqliteCardRepository()
    repo.add(card_payload(character="猫"))
    assert [c["id"] for c in repo.get_all()] == [c["id"] for c in models.get_all_cards()]


def test_card_repo_get_all_forwards_filters(fresh_db):
    repo = SqliteCardRepository()
    only_hiragana = repo.get_all(type_filter="hiragana")
    assert all(c["type"] == "hiragana" for c in only_hiragana)
    assert len(only_hiragana) > 0


def test_card_repo_get_all_forwards_jlpt_filter(fresh_db):
    """Sample data only seeds N5 cards, so an N3 card only shows up when
    jlpt_filter is actually reaching the query — not a default/no-op."""
    repo = SqliteCardRepository()
    assert repo.get_all(jlpt_filter="N3") == []

    n3_id = repo.add(card_payload(character="嵐", jlpt_level="N3"))
    result = repo.get_all(jlpt_filter="N3")
    assert [c["id"] for c in result] == [n3_id]


def test_card_repo_get_all_forwards_status_filter(fresh_db):
    repo = SqliteCardRepository()
    known_id = repo.add(card_payload(character="嵐", status="known"))
    repo.add(card_payload(character="虹", status="new"))

    result = repo.get_all(status_filter="known")
    assert known_id in [c["id"] for c in result]
    assert all(c["status"] == "known" for c in result)


def test_card_repo_get_all_forwards_favorite_only(fresh_db):
    repo = SqliteCardRepository()
    fav_id = repo.add(card_payload(character="嵐", is_favorite=1))
    repo.add(card_payload(character="虹", is_favorite=0))

    result = repo.get_all(favorite_only=True)
    assert fav_id in [c["id"] for c in result]
    assert all(c["is_favorite"] == 1 for c in result)


def test_card_repo_get_all_forwards_search(fresh_db):
    repo = SqliteCardRepository()
    target_id = repo.add(card_payload(character="嵐", meaning_vi="cơn bão hiếm gặp"))

    result = repo.get_all(search="hiếm gặp")
    assert [c["id"] for c in result] == [target_id]
    assert repo.get_all(search="cụm từ không tồn tại xyz") == []


def test_card_repo_get_all_forwards_include_deleted(fresh_db):
    repo = SqliteCardRepository()
    card_id = repo.add(card_payload(character="嵐"))
    repo.soft_delete(card_id)

    assert card_id not in [c["id"] for c in repo.get_all()]
    assert card_id in [c["id"] for c in repo.get_all(include_deleted=True)]


def test_card_repo_get_all_forwards_due_only(fresh_db):
    repo = SqliteCardRepository()
    study_repo = SqliteStudySessionRepository()
    card_id = repo.add(card_payload(character="嵐"))

    assert card_id in [c["id"] for c in repo.get_all(due_only=True)]
    study_repo.log(card_id, "correct")   # pushes srs_due_date into the future
    assert card_id not in [c["id"] for c in repo.get_all(due_only=True)]


def test_card_repo_get_all_forwards_limit_and_offset(fresh_db):
    repo = SqliteCardRepository()
    # Sample data already seeds 17 cards; just check limit/offset are honored,
    # not exact identities (those depend on created_at ordering of seed data).
    page1 = repo.get_all(limit=5, offset=0)
    page2 = repo.get_all(limit=5, offset=5)
    assert len(page1) == 5
    assert len(page2) == 5
    assert {c["id"] for c in page1}.isdisjoint({c["id"] for c in page2})


def test_card_repo_count_forwards_filters(fresh_db):
    repo = SqliteCardRepository()
    repo.add(card_payload(character="嵐", type="vocab", is_favorite=1))

    total = repo.count()
    fav_only = repo.count(favorite_only=True)
    vocab_only = repo.count(type_filter="vocab")

    assert fav_only < total
    assert vocab_only < total
    assert fav_only == len(repo.get_all(favorite_only=True))
    assert vocab_only == len(repo.get_all(type_filter="vocab"))


def test_card_repo_count_matches_models(fresh_db):
    repo = SqliteCardRepository()
    assert repo.count() == models.count_cards()


def test_card_repo_get_due_count_matches_models(fresh_db):
    repo = SqliteCardRepository()
    assert repo.get_due_count() == models.get_due_count()


def test_card_repo_update(fresh_db):
    repo = SqliteCardRepository()
    card_id = repo.add(card_payload())
    repo.update(card_id, card_payload(character="犬", meaning_vi="đổi rồi"))
    assert repo.get_by_id(card_id)["meaning_vi"] == "đổi rồi"


def test_card_repo_soft_delete_restore_hard_delete(fresh_db):
    repo = SqliteCardRepository()
    card_id = repo.add(card_payload())

    snapshot = repo.soft_delete(card_id)
    assert snapshot["id"] == card_id
    assert card_id not in [c["id"] for c in repo.get_all()]
    assert card_id in [c["id"] for c in repo.get_deleted()]

    repo.restore(card_id)
    assert card_id in [c["id"] for c in repo.get_all()]

    repo.hard_delete(card_id)
    assert repo.get_by_id(card_id) is None


def test_card_repo_toggle_favorite(fresh_db):
    repo = SqliteCardRepository()
    card_id = repo.add(card_payload(is_favorite=0))
    repo.toggle_favorite(card_id)
    assert repo.get_by_id(card_id)["is_favorite"] == 1


def test_card_repo_find_duplicates_forwards_exclude_id(fresh_db):
    repo = SqliteCardRepository()
    card_id = repo.add(card_payload(character="犬", type="vocab"))
    assert len(repo.find_duplicates("犬", "vocab")) == 1
    assert repo.find_duplicates("犬", "vocab", exclude_id=card_id) == []


def test_card_repo_bulk_operations(fresh_db):
    repo = SqliteCardRepository()
    ids = [repo.add(card_payload(character=c)) for c in "猫鳥魚"]

    repo.bulk_update_status(ids, "known")
    assert all(repo.get_by_id(i)["status"] == "known" for i in ids)

    repo.bulk_toggle_favorite(ids)
    assert all(repo.get_by_id(i)["is_favorite"] == 1 for i in ids)

    snapshots = repo.bulk_soft_delete(ids)
    assert {s["id"] for s in snapshots} == set(ids)
    assert all(i not in [c["id"] for c in repo.get_all()] for i in ids)


# ── DeckRepository ────────────────────────────────────────────────────────────

def test_deck_repo_add_update_delete(fresh_db):
    repo = SqliteDeckRepository()
    deck_id = repo.add("Bộ thẻ test", description="mô tả", color="#000000", icon="📚")
    deck = next(d for d in repo.get_all() if d["id"] == deck_id)
    assert deck["name"] == "Bộ thẻ test"

    repo.update(deck_id, "Đổi tên", "mô tả mới", "#111111", "🔥")
    deck = next(d for d in repo.get_all() if d["id"] == deck_id)
    assert deck["name"] == "Đổi tên"

    repo.delete(deck_id)
    assert deck_id not in [d["id"] for d in repo.get_all()]


def test_deck_repo_add_card_and_bulk_add_cards(fresh_db):
    card_repo = SqliteCardRepository()
    deck_repo = SqliteDeckRepository()

    deck_id = deck_repo.add("Bộ thẻ test")
    c1 = card_repo.add(card_payload(character="猫"))
    c2 = card_repo.add(card_payload(character="鳥"))

    deck_repo.add_card(deck_id, c1)
    deck_repo.bulk_add_cards(deck_id, [c1, c2])  # c1 already there — must not error

    ids_in_deck = [c["id"] for c in card_repo.get_all(deck_id=deck_id)]
    assert set(ids_in_deck) == {c1, c2}


def test_deck_repo_categories(fresh_db):
    repo = SqliteDeckRepository()
    cat_id = repo.add_category("Sách Kanji", icon="📘")
    assert any(c["id"] == cat_id for c in repo.get_all_categories())

    repo.update_category(cat_id, "Sách Kanji tập 1", "📗")
    cat = next(c for c in repo.get_all_categories() if c["id"] == cat_id)
    assert cat["name"] == "Sách Kanji tập 1"

    repo.delete_category(cat_id)
    assert cat_id not in [c["id"] for c in repo.get_all_categories()]


# ── StudySessionRepository ──────────────────────────────────────────────────

def test_study_session_repo_log_updates_status_and_srs(fresh_db):
    card_repo = SqliteCardRepository()
    study_repo = SqliteStudySessionRepository()

    card_id = card_repo.add(card_payload(status="new"))
    study_repo.log(card_id, "correct")

    card = card_repo.get_by_id(card_id)
    assert card["status"] == "learning"
    assert card["srs_interval"] > 1


def test_deck_repo_get_decks_for_card(fresh_db):
    card_repo = SqliteCardRepository()
    deck_repo = SqliteDeckRepository()

    card_id = card_repo.add(card_payload(character="嵐"))
    assert deck_repo.get_decks_for_card(card_id) == []

    d1 = deck_repo.add("Bộ thẻ A")
    d2 = deck_repo.add("Bộ thẻ B")
    deck_repo.add_card(d1, card_id)
    deck_repo.add_card(d2, card_id)

    decks = deck_repo.get_decks_for_card(card_id)
    assert {d["name"] for d in decks} == {"Bộ thẻ A", "Bộ thẻ B"}


def test_deck_repo_remove_card(fresh_db):
    card_repo = SqliteCardRepository()
    deck_repo = SqliteDeckRepository()

    card_id = card_repo.add(card_payload(character="嵐"))
    deck_id = deck_repo.add("Bộ thẻ test")
    deck_repo.add_card(deck_id, card_id)
    assert card_id in [
        c["id"] for c in card_repo.get_all(deck_id=deck_id)
    ]

    deck_repo.remove_card(deck_id, card_id)
    assert card_id not in [
        c["id"] for c in card_repo.get_all(deck_id=deck_id)
    ]

    # Removing again (already-removed card) must not raise.
    deck_repo.remove_card(deck_id, card_id)
