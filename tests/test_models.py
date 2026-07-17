"""
Tests for database/models.py — the data-access layer.

Run with:  pytest tests/ -v
"""
import pytest

from database import models
from database.models import DBError
from tests.conftest import card_payload


# ── init_db / sample data ───────────────────────────────────────────────────

def test_init_db_seeds_sample_data(fresh_db):
    cards = models.get_all_cards()
    decks = models.get_all_decks()
    assert len(cards) == 17
    assert len(decks) == 3


# ── Basic CRUD ───────────────────────────────────────────────────────────────

def test_add_card_and_get_by_id(fresh_db):
    new_id = models.add_card(card_payload(character="猫", meaning_vi="con mèo"))
    card = models.get_card_by_id(new_id)
    assert card is not None
    assert card["character"] == "猫"
    assert card["meaning_vi"] == "con mèo"
    assert card["deleted_at"] is None


def test_get_card_by_id_missing_returns_none(fresh_db):
    assert models.get_card_by_id(999999) is None


def test_update_card(fresh_db):
    card_id = models.add_card(card_payload())
    payload = card_payload(character="犬", meaning_vi="thay đổi rồi")
    models.update_card(card_id, payload)
    card = models.get_card_by_id(card_id)
    assert card["meaning_vi"] == "thay đổi rồi"


# ── Soft delete / restore / hard delete ──────────────────────────────────────

def test_soft_delete_then_restore(fresh_db):
    card_id = models.add_card(card_payload())
    snapshot = models.soft_delete_card(card_id)
    assert snapshot["id"] == card_id

    # Soft-deleted cards are excluded from the default listing...
    assert card_id not in [c["id"] for c in models.get_all_cards()]
    # ...but visible in the trash.
    assert card_id in [c["id"] for c in models.get_deleted_cards()]

    models.restore_card(card_id)
    assert card_id in [c["id"] for c in models.get_all_cards()]
    assert card_id not in [c["id"] for c in models.get_deleted_cards()]


def test_soft_delete_missing_card_returns_none(fresh_db):
    assert models.soft_delete_card(999999) is None


def test_hard_delete_removes_permanently(fresh_db):
    card_id = models.add_card(card_payload())
    models.hard_delete_card(card_id)
    assert models.get_card_by_id(card_id) is None


# ── Favorite toggle ───────────────────────────────────────────────────────────

def test_toggle_favorite(fresh_db):
    card_id = models.add_card(card_payload(is_favorite=0))
    models.toggle_favorite(card_id)
    assert models.get_card_by_id(card_id)["is_favorite"] == 1
    models.toggle_favorite(card_id)
    assert models.get_card_by_id(card_id)["is_favorite"] == 0


# ── Duplicate detection ───────────────────────────────────────────────────────

def test_find_duplicates_detects_same_character_and_type(fresh_db):
    models.add_card(card_payload(character="犬", type="vocab"))
    dupes = models.find_duplicates("犬", "vocab")
    assert len(dupes) == 1


def test_find_duplicates_ignores_different_type(fresh_db):
    models.add_card(card_payload(character="犬", type="vocab"))
    dupes = models.find_duplicates("犬", "kanji")
    assert dupes == []


def test_find_duplicates_excludes_given_id(fresh_db):
    card_id = models.add_card(card_payload(character="犬", type="vocab"))
    dupes = models.find_duplicates("犬", "vocab", exclude_id=card_id)
    assert dupes == []


# ── Filtering / search / counting ────────────────────────────────────────────

def test_get_all_cards_type_filter(fresh_db):
    models.add_card(card_payload(character="猫", type="vocab"))
    only_hiragana = models.get_all_cards(type_filter="hiragana")
    assert all(c["type"] == "hiragana" for c in only_hiragana)
    assert len(only_hiragana) > 0


def test_get_all_cards_search_matches_meaning(fresh_db):
    models.add_card(card_payload(character="猫", meaning_vi="con mèo xám"))
    results = models.get_all_cards(search="mèo")
    assert any(c["character"] == "猫" for c in results)


def test_get_all_cards_favorite_only(fresh_db):
    fav_id = models.add_card(card_payload(character="猫", is_favorite=1))
    models.add_card(card_payload(character="鳥", is_favorite=0))
    favs = models.get_all_cards(favorite_only=True)
    assert all(c["is_favorite"] == 1 for c in favs)
    assert fav_id in [c["id"] for c in favs]


def test_get_all_cards_excludes_deleted_by_default(fresh_db):
    card_id = models.add_card(card_payload(character="猫"))
    models.soft_delete_card(card_id)
    assert card_id not in [c["id"] for c in models.get_all_cards()]
    assert card_id in [c["id"] for c in models.get_all_cards(include_deleted=True)]


def test_card_can_belong_to_multiple_decks(fresh_db):
    """A single card should be assignable to more than one deck at once
    (deck_cards is a many-to-many join table, not a single deck_id column)."""
    deck_a = models.add_deck("Deck A")
    deck_b = models.add_deck("Deck B")
    card_id = models.add_card(card_payload(character="花"))

    models.add_card_to_deck(deck_a, card_id)
    models.add_card_to_deck(deck_b, card_id)

    ids_in_a = [c["id"] for c in models.get_all_cards(deck_id=deck_a)]
    ids_in_b = [c["id"] for c in models.get_all_cards(deck_id=deck_b)]
    assert card_id in ids_in_a
    assert card_id in ids_in_b


def test_get_all_cards_filters_by_deck(fresh_db):
    """Regression test: get_all_cards(deck_id=...) JOINs deck_cards, which
    has its own `id` column — the SELECT list must qualify cards.id or
    SQLite raises 'ambiguous column name: id'."""
    deck_id = models.add_deck("Test Deck")
    in_deck = models.add_card(card_payload(character="猫"))
    not_in_deck = models.add_card(card_payload(character="鳥"))
    models.add_card_to_deck(deck_id, in_deck)

    result_ids = [c["id"] for c in models.get_all_cards(deck_id=deck_id)]
    assert result_ids == [in_deck]
    assert not_in_deck not in result_ids


def test_count_cards_filters_by_deck(fresh_db):
    deck_id = models.add_deck("Test Deck")
    in_deck = models.add_card(card_payload(character="猫"))
    models.add_card(card_payload(character="鳥"))
    models.add_card_to_deck(deck_id, in_deck)
    assert models.count_cards(deck_id=deck_id) == 1



    models.add_card(card_payload(character="猫"))
    assert models.count_cards() == len(models.get_all_cards())
    assert models.count_cards(type_filter="vocab") == len(
        models.get_all_cards(type_filter="vocab"))


# ── Bulk operations ───────────────────────────────────────────────────────────

def test_bulk_update_status(fresh_db):
    ids = [models.add_card(card_payload(character=c)) for c in "猫鳥魚"]
    models.bulk_update_status(ids, "known")
    for i in ids:
        assert models.get_card_by_id(i)["status"] == "known"


def test_bulk_update_status_noop_on_empty_list(fresh_db):
    # Should not raise even with no ids.
    models.bulk_update_status([], "known")


def test_bulk_toggle_favorite(fresh_db):
    ids = [models.add_card(card_payload(character=c, is_favorite=0)) for c in "猫鳥"]
    models.bulk_toggle_favorite(ids)
    for i in ids:
        assert models.get_card_by_id(i)["is_favorite"] == 1


def test_bulk_soft_delete_returns_snapshots(fresh_db):
    ids = [models.add_card(card_payload(character=c)) for c in "猫鳥"]
    snapshots = models.bulk_soft_delete(ids)
    assert {s["id"] for s in snapshots} == set(ids)
    for i in ids:
        assert i not in [c["id"] for c in models.get_all_cards()]


# ── Study session logic (status progression) ────────────────────────────────

def test_log_study_correct_progresses_new_to_learning(fresh_db):
    card_id = models.add_card(card_payload(status="new"))
    models.log_study(card_id, "correct")
    assert models.get_card_by_id(card_id)["status"] == "learning"


def test_log_study_correct_progresses_learning_to_known(fresh_db):
    card_id = models.add_card(card_payload(status="learning"))
    models.log_study(card_id, "correct")
    assert models.get_card_by_id(card_id)["status"] == "known"


def test_log_study_incorrect_regresses_known_to_learning(fresh_db):
    card_id = models.add_card(card_payload(status="known"))
    models.log_study(card_id, "incorrect")
    assert models.get_card_by_id(card_id)["status"] == "learning"


def test_log_study_incorrect_resets_learning_to_new(fresh_db):
    card_id = models.add_card(card_payload(status="learning"))
    models.log_study(card_id, "incorrect")
    assert models.get_card_by_id(card_id)["status"] == "new"


# ── SRS (spaced repetition) ──────────────────────────────────────────────────

def test_new_card_is_due_immediately(fresh_db):
    card_id = models.add_card(card_payload())
    assert card_id in [c["id"] for c in models.get_all_cards(due_only=True)]


def test_correct_answer_pushes_card_out_of_due_list(fresh_db):
    card_id = models.add_card(card_payload())
    models.log_study(card_id, "correct")
    due_ids = [c["id"] for c in models.get_all_cards(due_only=True)]
    assert card_id not in due_ids


def test_new_card_starts_at_default_ease(fresh_db):
    card_id = models.add_card(card_payload())
    assert models.get_card_by_id(card_id)["srs_ease"] == models.SRS_DEFAULT_EASE


def test_correct_answer_grows_interval_and_ease(fresh_db):
    card_id = models.add_card(card_payload())
    models.log_study(card_id, "correct")
    card = models.get_card_by_id(card_id)
    assert card["srs_interval"] > 1
    assert card["srs_ease"] > models.SRS_DEFAULT_EASE


def test_repeated_correct_answers_grow_interval_faster_over_time(fresh_db):
    """Consecutive correct answers should raise the ease factor, so each
    successive interval jump is proportionally bigger than the last —
    this is what distinguishes SM-2-style scheduling from flat doubling."""
    card_id = models.add_card(card_payload())
    intervals = []
    for _ in range(4):
        models.log_study(card_id, "correct")
        intervals.append(models.get_card_by_id(card_id)["srs_interval"])
    # Each jump should be at least as big as the previous one (non-decreasing growth)
    growth = [b - a for a, b in zip(intervals, intervals[1:])]
    assert all(g2 >= g1 for g1, g2 in zip(growth, growth[1:])), intervals


def test_interval_growth_is_capped(fresh_db):
    card_id = models.add_card(card_payload())
    for _ in range(15):   # far more than needed to hit the cap
        models.log_study(card_id, "correct")
    assert models.get_card_by_id(card_id)["srs_interval"] == models.SRS_MAX_INTERVAL_DAYS


def test_ease_is_capped_at_max(fresh_db):
    card_id = models.add_card(card_payload())
    for _ in range(20):
        models.log_study(card_id, "correct")
    assert models.get_card_by_id(card_id)["srs_ease"] == models.SRS_MAX_EASE


def test_incorrect_answer_resets_interval_and_lowers_ease(fresh_db):
    card_id = models.add_card(card_payload())
    models.log_study(card_id, "correct")
    models.log_study(card_id, "correct")
    ease_before = models.get_card_by_id(card_id)["srs_ease"]
    interval_before = models.get_card_by_id(card_id)["srs_interval"]
    assert interval_before > 1

    models.log_study(card_id, "incorrect")
    card = models.get_card_by_id(card_id)
    assert card["srs_interval"] == 1
    assert card["srs_ease"] < ease_before
    # due_date should be "tomorrow", so NOT due today
    assert card_id not in [c["id"] for c in models.get_all_cards(due_only=True)]


def test_ease_is_floored_at_min(fresh_db):
    card_id = models.add_card(card_payload())
    for _ in range(20):
        models.log_study(card_id, "incorrect")
    assert models.get_card_by_id(card_id)["srs_ease"] == models.SRS_MIN_EASE


def test_get_due_count_matches_due_only_listing(fresh_db):
    assert models.get_due_count() == len(models.get_all_cards(due_only=True))
    card_id = models.add_card(card_payload())
    models.log_study(card_id, "correct")
    assert models.get_due_count() == len(models.get_all_cards(due_only=True))


# ── _compute_srs_update (pure function, no DB) ──────────────────────────────

def test_compute_srs_correct_increases_interval_and_ease():
    new_interval, new_ease = models._compute_srs_update(1, 2.5, "correct")
    assert new_interval > 1
    assert new_ease == 2.6


def test_compute_srs_correct_always_grows_by_at_least_one_day():
    """Guards against interval*ease rounding down to a no-op (e.g. at
    low ease values), which would make a card that's answered correctly
    never actually move further out."""
    new_interval, _ = models._compute_srs_update(1, 1.3, "correct")
    assert new_interval >= 2


def test_compute_srs_incorrect_resets_to_one_day():
    new_interval, _ = models._compute_srs_update(45, 2.7, "incorrect")
    assert new_interval == 1


def test_compute_srs_ease_never_exceeds_max():
    _, new_ease = models._compute_srs_update(10, models.SRS_MAX_EASE, "correct")
    assert new_ease == models.SRS_MAX_EASE


def test_compute_srs_ease_never_drops_below_min():
    _, new_ease = models._compute_srs_update(1, models.SRS_MIN_EASE, "incorrect")
    assert new_ease == models.SRS_MIN_EASE


def test_compute_srs_interval_never_exceeds_cap():
    new_interval, _ = models._compute_srs_update(80, 2.8, "correct")
    assert new_interval == models.SRS_MAX_INTERVAL_DAYS




def test_deck_crud_cycle(fresh_db):
    deck_id = models.add_deck("Test Deck", "mô tả", "#123456", "🎌")
    decks = {d["id"]: d for d in models.get_all_decks()}
    assert decks[deck_id]["name"] == "Test Deck"

    models.update_deck(deck_id, "Renamed", "mô tả mới", "#654321", "📘")
    decks = {d["id"]: d for d in models.get_all_decks()}
    assert decks[deck_id]["name"] == "Renamed"

    models.delete_deck(deck_id)
    assert deck_id not in {d["id"] for d in models.get_all_decks()}


def test_add_card_to_deck_increments_card_count(fresh_db):
    deck_id = models.add_deck("My Deck")
    card_id = models.add_card(card_payload())
    models.add_card_to_deck(deck_id, card_id)
    decks = {d["id"]: d for d in models.get_all_decks()}
    assert decks[deck_id]["card_count"] == 1


def test_bulk_add_to_deck_adds_all_cards(fresh_db):
    deck_id = models.add_deck("My Deck")
    ids = [models.add_card(card_payload(character=c)) for c in "猫鳥魚"]
    models.bulk_add_to_deck(deck_id, ids)
    in_deck_ids = [c["id"] for c in models.get_all_cards(deck_id=deck_id)]
    assert set(in_deck_ids) == set(ids)


def test_bulk_add_to_deck_is_idempotent_on_duplicates(fresh_db):
    """Calling it twice (or with a card already in the deck) must not error
    or double-count — deck_cards has no room for duplicate (deck_id, card_id)."""
    deck_id = models.add_deck("My Deck")
    card_id = models.add_card(card_payload())
    models.bulk_add_to_deck(deck_id, [card_id])
    models.bulk_add_to_deck(deck_id, [card_id])   # again — should be a no-op
    decks = {d["id"]: d for d in models.get_all_decks()}
    assert decks[deck_id]["card_count"] == 1


def test_bulk_add_to_deck_noop_on_empty_list(fresh_db):
    deck_id = models.add_deck("My Deck")
    models.bulk_add_to_deck(deck_id, [])   # should not raise
    decks = {d["id"]: d for d in models.get_all_decks()}
    assert decks[deck_id]["card_count"] == 0


# ── Stats ─────────────────────────────────────────────────────────────────────

def test_get_stats_totals_match_card_count(fresh_db):
    stats = models.get_stats()
    assert stats["total"] == len(models.get_all_cards())
    assert isinstance(stats["by_type"], dict)


def test_get_full_stats_has_expected_keys(fresh_db):
    stats = models.get_full_stats()
    for key in ("total", "by_type", "by_status", "by_jlpt", "favorites",
                "daily_added", "completeness", "sources",
                "total_sessions", "correct_sessions", "daily_study", "deck_sizes"):
        assert key in stats


# ── Error handling ────────────────────────────────────────────────────────────

def test_add_card_invalid_type_raises_dberror(fresh_db):
    """The `type` column has a CHECK constraint; violating it must
    surface as our own DBError, not a raw sqlite3 exception."""
    with pytest.raises(DBError):
        models.add_card(card_payload(type="not_a_real_type"))


def test_add_deck_duplicate_name_raises_dberror(fresh_db):
    """`decks.name` is UNIQUE."""
    models.add_deck("Cùng tên")
    with pytest.raises(DBError):
        models.add_deck("Cùng tên")
