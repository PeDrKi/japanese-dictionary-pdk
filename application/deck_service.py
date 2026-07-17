"""
application/deck_service.py — use cases for decks and deck categories.

Thin pass-through to domain.repositories.DeckRepository — no extra
business rule was found in ui/ beyond what DeckRepository already does
(see database/_decks.py). Exists mainly so ui/ has one boundary to
depend on (application.*) for every feature area, consistent with
CardService/StudyService/StatsService, rather than importing the
repository interface directly in some places and a service in others.
"""
from domain.repositories import DeckRepository


class DeckService:
    def __init__(self, decks: DeckRepository):
        self._decks = decks

    # ── Decks ────────────────────────────────────────────────────────────────

    def list_decks(self) -> list[dict]:
        return self._decks.get_all()

    def add(self, name: str, description: str = "", color: str = "#4A90D9",
            icon: str = "📁", category_id=None) -> int:
        return self._decks.add(name, description, color, icon, category_id)

    def update(self, deck_id: int, name: str, description: str,
               color: str, icon: str, category_id=None) -> None:
        self._decks.update(deck_id, name, description, color, icon, category_id)

    def delete(self, deck_id: int) -> None:
        self._decks.delete(deck_id)

    def add_card(self, deck_id: int, card_id: int) -> None:
        self._decks.add_card(deck_id, card_id)

    def remove_card(self, deck_id: int, card_id: int) -> None:
        self._decks.remove_card(deck_id, card_id)

    def bulk_add_cards(self, deck_id: int, ids: list) -> None:
        self._decks.bulk_add_cards(deck_id, ids)

    # ── Categories ───────────────────────────────────────────────────────────

    def list_categories(self) -> list[dict]:
        return self._decks.get_all_categories()

    def add_category(self, name: str, icon: str = "🗂️") -> int:
        return self._decks.add_category(name, icon)

    def update_category(self, category_id: int, name: str, icon: str) -> None:
        self._decks.update_category(category_id, name, icon)

    def delete_category(self, category_id: int) -> None:
        self._decks.delete_category(category_id)

    def get_decks_for_card(self, card_id: int) -> list[dict]:
        return self._decks.get_decks_for_card(card_id)
