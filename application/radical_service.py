"""
application/radical_service.py — use cases for radicals (bộ thủ) and
card-to-radical assignment.

Thin pass-through to domain.repositories.RadicalRepository, same shape
as DeckService — exists so ui/ has one boundary (application.*) to
depend on for this feature too, rather than importing the repository
interface directly.
"""
from domain.repositories import RadicalRepository


class RadicalService:
    def __init__(self, radicals: RadicalRepository):
        self._radicals = radicals

    def list_radicals(self) -> list[dict]:
        return self._radicals.get_all()

    def add(self, character: str, name: str = "", color: str = "#4A90D9") -> int:
        return self._radicals.add(character, name, color)

    def update(self, radical_id: int, character: str, name: str, color: str) -> None:
        self._radicals.update(radical_id, character, name, color)

    def delete(self, radical_id: int) -> None:
        self._radicals.delete(radical_id)

    def reorder(self, ordered_ids: list) -> None:
        """Persist a new drag-and-drop order for the radical list itself."""
        self._radicals.reorder(ordered_ids)

    def add_card(self, radical_id: int, card_id: int) -> None:
        self._radicals.add_card(radical_id, card_id)

    def remove_card(self, radical_id: int, card_id: int) -> None:
        self._radicals.remove_card(radical_id, card_id)

    def get_radicals_for_card(self, card_id: int) -> list[dict]:
        return self._radicals.get_radicals_for_card(card_id)

    def get_cards_for_radical(self, radical_id: int) -> list[dict]:
        """Every card the user has placed in this bộ — the "tra cứu 1 bộ
        gồm nhiều từ thuộc bộ đó" lookup."""
        return self._radicals.get_cards_for_radical(radical_id)
