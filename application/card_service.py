"""
application/card_service.py — use cases for creating, editing, and
querying cards.

Depends only on domain.repositories.CardRepository (an interface, not
infrastructure.db.sqlite_repositories directly) and on pure domain
logic (domain.validators). The concrete repository is handed in via the
constructor by whatever composes the app (currently just tests; ui/ will
do this once it's migrated in a later stage).

validate_and_build() exists because this exact three-step dance —
validate required fields, truncate character/meaning_vi, then shape the
full data dict — currently lives inline in ui/card_form.py's _save().
Pulling it out here means: (1) it's unit testable without opening a
CustomTkinter dialog, (2) when ui/card_form.py is migrated to call this
service instead of database.models directly, _save() shrinks to reading
widget values + calling this + showing the result — no business rule
left in the widget code.

Duplicate-checking is exposed as its own method (check_duplicates)
rather than folded into validate_and_build, because in the UI it drives
a confirmation dialog ("thẻ này đã tồn tại, vẫn lưu?") — a UI decision
this service should not make on the caller's behalf.
"""
from constants import MAX_CHARACTER_LEN, MAX_MEANING_LEN
from domain.repositories import CardRepository
from domain.validators import truncate, validate_required, build_card_data


class CardService:
    def __init__(self, cards: CardRepository):
        self._cards = cards

    # ── Queries ──────────────────────────────────────────────────────────────

    def list_cards(self, **filters) -> list[dict]:
        """Accepts the same filter kwargs as CardRepository.get_all
        (type_filter, jlpt_filter, status_filter, favorite_only, deck_id,
        search, include_deleted, due_only, limit, offset)."""
        return self._cards.get_all(**filters)

    def count(self, **filters) -> int:
        return self._cards.count(**filters)

    def due_count(self) -> int:
        return self._cards.get_due_count()

    def get(self, card_id: int):
        return self._cards.get_by_id(card_id)

    def get_deleted(self) -> list[dict]:
        return self._cards.get_deleted()

    def check_duplicates(self, character: str, card_type: str, exclude_id=None) -> list[dict]:
        """
        Note for the future UI caller: ui/card_form.py's original _save()
        runs the duplicate check on the already-truncated character (after
        validate_required passes, before build_card_data). To reproduce
        that exact ordering, call validate_and_build() first and pass its
        returned data["character"] here — not the raw widget text — so
        the dedup check sees the same value that will actually be stored.
        In practice MAX_CHARACTER_LEN (50) is far above any real card's
        length so this rarely changes the result, but it's the contract
        to preserve if migrating _save() verbatim.
        """
        return self._cards.find_duplicates(character, card_type, exclude_id=exclude_id)

    # ── Validation + shaping ─────────────────────────────────────────────────

    def validate_and_build(self, *, card_type, character, meaning_vi, **rest):
        """
        Mirrors ui/card_form.py's _save() pre-processing exactly:
        validate the two required fields, truncate them, then shape the
        full card dict via domain.validators.build_card_data.

        Returns (data, check) where:
          - on success: data is the dict ready for CardRepository.add()/
            update(), check == {"character": True, "meaning_vi": True,
            "valid": True}
          - on failure: data is None, check tells the caller which
            field(s) failed (same shape returned by validate_required),
            so a UI caller can decide how to highlight them.
        """
        check = validate_required(character, meaning_vi)
        if not check["valid"]:
            return None, check

        character = truncate(character.strip(), MAX_CHARACTER_LEN)
        meaning_vi = truncate(meaning_vi.strip(), MAX_MEANING_LEN)
        data = build_card_data(
            card_type=card_type, character=character, meaning_vi=meaning_vi, **rest
        )
        return data, check

    # ── Commands ─────────────────────────────────────────────────────────────

    def add(self, data: dict) -> int:
        return self._cards.add(data)

    def update(self, card_id: int, data: dict) -> None:
        self._cards.update(card_id, data)

    def soft_delete(self, card_id: int):
        return self._cards.soft_delete(card_id)

    def restore(self, card_id: int) -> None:
        self._cards.restore(card_id)

    def hard_delete(self, card_id: int) -> None:
        self._cards.hard_delete(card_id)

    def toggle_favorite(self, card_id: int) -> None:
        self._cards.toggle_favorite(card_id)

    def bulk_update_status(self, ids: list, status: str) -> None:
        self._cards.bulk_update_status(ids, status)

    def bulk_toggle_favorite(self, ids: list) -> None:
        self._cards.bulk_toggle_favorite(ids)

    def bulk_soft_delete(self, ids: list) -> list[dict]:
        return self._cards.bulk_soft_delete(ids)
