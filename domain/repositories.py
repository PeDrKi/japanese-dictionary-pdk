"""
domain/repositories.py — repository interfaces (Stage 2 of the clean-
architecture migration).

These are Protocols, not ABCs: any object with matching method
signatures satisfies the interface (structural typing), so the concrete
SQLite implementation in infrastructure/db/sqlite_repositories.py doesn't
need to explicitly subclass anything, and a future in-memory fake for
tests doesn't either.

Method signatures here mirror the existing free functions in
database/_cards.py, database/_decks.py, database/_study.py one-for-one —
Stage 2 only adds a boundary in front of the working SQL, it does not
change what any operation does. Return shapes are still plain dict /
list[dict], same as today's database.models — introducing real domain
entities (e.g. a Card dataclass) is a separate, later decision (see the
refactor plan, section 5) and not required for this boundary to be
useful.

Nothing outside domain/ is imported here — a repository interface is
part of the domain, defined by what the business logic needs, not by
what SQLite happens to make convenient.
"""
from typing import Optional, Protocol


class CardRepository(Protocol):
    """Everything needed to read/write `cards`. Mirrors database/_cards.py."""

    def get_all(self, *, type_filter=None, jlpt_filter=None, status_filter=None,
                favorite_only=False, deck_id=None, search=None,
                include_deleted=False, due_only=False,
                limit=None, offset=0) -> list[dict]: ...

    def count(self, *, type_filter=None, jlpt_filter=None, status_filter=None,
              favorite_only=False, deck_id=None, search=None,
              due_only=False) -> int: ...

    def get_due_count(self) -> int: ...

    def get_by_id(self, card_id: int) -> Optional[dict]: ...

    def add(self, data: dict) -> int: ...

    def update(self, card_id: int, data: dict) -> None: ...

    def soft_delete(self, card_id: int) -> Optional[dict]:
        """Returns a snapshot dict of the card as it was, or None if not found."""
        ...

    def restore(self, card_id: int) -> None: ...

    def hard_delete(self, card_id: int) -> None: ...

    def get_deleted(self) -> list[dict]: ...

    def toggle_favorite(self, card_id: int) -> None: ...

    def find_duplicates(self, character: str, card_type: str,
                         exclude_id: Optional[int] = None) -> list[dict]: ...

    def bulk_update_status(self, ids: list, status: str) -> None: ...

    def bulk_toggle_favorite(self, ids: list) -> None: ...

    def bulk_soft_delete(self, ids: list) -> list[dict]: ...


class DeckRepository(Protocol):
    """Decks, deck-categories, and card-to-deck assignment.
    Mirrors database/_decks.py."""

    def get_all(self) -> list[dict]: ...

    def add(self, name: str, description: str = "", color: str = "#4A90D9",
            icon: str = "📁", category_id: Optional[int] = None) -> int: ...

    def update(self, deck_id: int, name: str, description: str,
               color: str, icon: str, category_id: Optional[int] = None) -> None: ...

    def delete(self, deck_id: int) -> None: ...

    def add_card(self, deck_id: int, card_id: int) -> None: ...

    def remove_card(self, deck_id: int, card_id: int) -> None:
        """Mirrors add_card. Added in Stage 4 alongside the UI migration
        for the same reason as get_decks_for_card — the deck-membership
        checkbox dialog needed to remove a card from a deck and no
        repository method covered it."""
        ...

    def bulk_add_cards(self, deck_id: int, ids: list) -> None: ...

    def get_all_categories(self) -> list[dict]: ...

    def add_category(self, name: str, icon: str = "🗂️") -> int: ...

    def update_category(self, category_id: int, name: str, icon: str) -> None: ...

    def delete_category(self, category_id: int) -> None: ...

    def get_decks_for_card(self, card_id: int) -> list[dict]:
        """Every deck a given card belongs to. Added in Stage 4 alongside
        the UI migration — ui/card_detail.py needed this and no existing
        repository method covered it (it was a raw connection query
        inline in the UI file), so the query moved to
        database/_decks.py.get_decks_for_card() first, then got a
        boundary here like everything else."""
        ...


class StudySessionRepository(Protocol):
    """Recording a study attempt and applying its effect on the card
    (status + SRS scheduling). Mirrors database/_study.py.

    Kept as a single `log()` call — matching today's log_study() — rather
    than split into "read card / apply domain.srs rule / save card"
    (which would need a real Card entity to pass between application and
    infrastructure). That split is a reasonable next step but isn't
    required for Stage 2's goal: give UI a boundary to call through
    instead of `database.models` directly.
    """

    def log(self, card_id: int, result: str) -> None: ...


class StatsRepository(Protocol):
    """Dashboard statistics — read-only. Mirrors database/_stats.py.

    Added in Stage 3 (not Stage 2, alongside the other three) because it
    only became needed once StatsService needed something to depend on —
    everything else about it follows the same rule as the Stage 2
    interfaces: shape mirrors the existing free function 1:1, no new
    behavior.
    """

    def get_summary(self) -> dict: ...

    def get_full(self) -> dict: ...


class KanjiIdsRepository(Protocol):
    """Ideographic Description Sequence lookup — one character to its raw
    IDS breakdown string (e.g. "暗" -> "⿰日音"), or None if there's no
    record for it. Mirrors infrastructure/kanji_ids.py, which reads this
    from a bundled offline data file (no DB, no network).

    Backs the kanji-decomposition feature (ui/kanji_decomposition_dialog.py
    via application/decomposition_service.py)."""

    def get_ids(self, character: str) -> Optional[str]: ...


class RadicalRepository(Protocol):
    """User-managed bộ thủ (radical) groups and their card membership.
    Structurally the same shape as DeckRepository (a named group with a
    many-to-many link to cards), but radicals also have a user-controlled
    display order (see reorder — the radical list is drag-to-reorder in
    the UI) and no categories.

    Unlike domain.kanji_decomposition, nothing here is derived from IDS
    data — which cards belong to which bộ is entered by the user, via
    drag-and-drop in ui/radical_view.py."""

    def get_all(self) -> list: ...

    def add(self, character: str, name: str = "", color: str = "#4A90D9") -> int: ...

    def update(self, radical_id: int, character: str, name: str, color: str) -> None: ...

    def delete(self, radical_id: int) -> None: ...

    def reorder(self, ordered_ids: list) -> None: ...

    def add_card(self, radical_id: int, card_id: int) -> None: ...

    def remove_card(self, radical_id: int, card_id: int) -> None: ...

    def get_radicals_for_card(self, card_id: int) -> list: ...

    def get_cards_for_radical(self, radical_id: int) -> list: ...


class UserDecompositionRepository(Protocol):
    """User-defined "chữ này gồm những bộ nào" overrides — takes priority
    over KanjiIdsRepository's bundled offline dataset for whichever
    characters the user has defined one for. `parts` is every component
    character concatenated (e.g. "日音" = 2 parts). Mirrors
    infrastructure/db/sqlite_repositories.py's SqliteUserDecompositionRepository.

    Consumed by application/decomposition_service.py."""

    def get_parts(self, character: str) -> Optional[str]: ...

    def set_parts(self, character: str, parts: str) -> None: ...

    def delete(self, character: str) -> None: ...

    def get_all(self) -> list: ...
