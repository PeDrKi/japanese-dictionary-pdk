"""
models.py — public API facade for the database layer.

This used to be one 555-line file containing everything (connection
pooling, cards, decks, stats, SRS). It's now split into focused
submodules for maintainability:

    _common.py  — connection pooling, DBError, @_db_op decorator
    _cards.py   — card CRUD, search/filter, bulk operations
    _decks.py   — deck CRUD, card-to-deck assignment
    _stats.py   — dashboard statistics
    _study.py   — SRS scheduling + study-session logging

This file just re-exports everything from those submodules, so every
existing call site keeps working unchanged — both
`from database.models import add_card` and
`from database import models; models.add_card(...)`.
"""
from ._common import (
    DBError,
    get_connection,
    close_thread_connection,
)
from ._cards import (
    get_all_cards,
    count_cards,
    get_due_count,
    get_card_by_id,
    add_card,
    update_card,
    soft_delete_card,
    restore_card,
    hard_delete_card,
    get_deleted_cards,
    toggle_favorite,
    find_duplicates,
    bulk_update_status,
    bulk_toggle_favorite,
    bulk_soft_delete,
)
from ._decks import (
    get_all_decks,
    add_deck,
    update_deck,
    delete_deck,
    add_card_to_deck,
    remove_card_from_deck,
    bulk_add_to_deck,
    get_decks_for_card,
    get_all_categories,
    add_category,
    update_category,
    delete_category,
)
from ._stats import (
    get_stats,
    get_full_stats,
)
from ._study import (
    log_study,
    _compute_srs_update,
    SRS_MAX_INTERVAL_DAYS,
    SRS_MIN_EASE,
    SRS_MAX_EASE,
    SRS_EASE_STEP,
    SRS_EASE_PENALTY,
    SRS_DEFAULT_EASE,
)

__all__ = [
    "DBError", "get_connection", "close_thread_connection",
    "get_all_cards", "count_cards", "get_due_count", "get_card_by_id",
    "add_card", "update_card", "soft_delete_card", "restore_card",
    "hard_delete_card", "get_deleted_cards", "toggle_favorite",
    "find_duplicates", "bulk_update_status", "bulk_toggle_favorite",
    "bulk_soft_delete",
    "get_all_decks", "add_deck", "update_deck", "delete_deck",
    "add_card_to_deck", "remove_card_from_deck", "bulk_add_to_deck", "get_decks_for_card",
    "get_all_categories", "add_category", "update_category", "delete_category",
    "get_stats", "get_full_stats",
    "log_study", "_compute_srs_update",
    "SRS_MAX_INTERVAL_DAYS", "SRS_MIN_EASE", "SRS_MAX_EASE",
    "SRS_EASE_STEP", "SRS_EASE_PENALTY", "SRS_DEFAULT_EASE",
]
