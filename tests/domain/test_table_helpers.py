"""
Tests for utils/table_helpers.py — pure sort/column-width logic extracted
from ui/table_view.py. No Tk/Treeview needed.
"""
from domain.table_helpers import sort_cards, sort_key, clamp_column_widths


def _cards():
    return [
        {"id": 3, "character": "犬", "stroke_count": 4},
        {"id": 1, "character": "猫", "stroke_count": None},
        {"id": 2, "character": "あ", "stroke_count": 10},
    ]


# ── sort_cards / sort_key ────────────────────────────────────────────────────

def test_sort_cards_numeric_ascending():
    result = sort_cards(_cards(), "id", ascending=True)
    assert [c["id"] for c in result] == [1, 2, 3]


def test_sort_cards_numeric_descending():
    result = sort_cards(_cards(), "id", ascending=False)
    assert [c["id"] for c in result] == [3, 2, 1]


def test_sort_cards_does_not_mutate_input():
    original = _cards()
    original_order = [c["id"] for c in original]
    sort_cards(original, "id", ascending=False)
    assert [c["id"] for c in original] == original_order


def test_sort_cards_numeric_none_sorts_last_ascending():
    result = sort_cards(_cards(), "stroke_count", ascending=True)
    # None (card id=1) should be last regardless of numeric value
    assert result[-1]["id"] == 1


def test_sort_cards_text_column_case_insensitive():
    """Sorting is case-insensitive (but plain Unicode codepoint order —
    not locale-aware Vietnamese collation, which the app doesn't implement)."""
    cards = [{"id": 1, "meaning_vi": "Bò"}, {"id": 2, "meaning_vi": "bó"}]
    result = sort_cards(cards, "meaning_vi", ascending=True)
    # "Bò" and "bò" would tie if not lowercased first; case-fold must apply
    assert sort_key(cards[0], "meaning_vi") == "bò"


def test_sort_key_missing_field_treated_as_empty():
    assert sort_key({}, "meaning_vi") == ""
    assert sort_key({}, "id") == (True, 0)


# ── clamp_column_widths ──────────────────────────────────────────────────────

_COLUMNS = [
    ("id", "ID", 45, False),
    ("character", "Ký tự", 90, True),
]


def test_clamp_uses_saved_width_when_valid():
    result = clamp_column_widths({"id": 60, "character": 120}, _COLUMNS)
    assert result == {"id": 60, "character": 120}


def test_clamp_falls_back_to_default_when_missing():
    result = clamp_column_widths({}, _COLUMNS)
    assert result == {"id": 45, "character": 90}


def test_clamp_rejects_corrupted_non_numeric_value():
    result = clamp_column_widths({"id": "not_a_number"}, _COLUMNS)
    assert result["id"] == 45   # falls back to default


def test_clamp_enforces_min_and_max():
    result = clamp_column_widths({"id": 1, "character": 99999}, _COLUMNS,
                                  min_width=40, max_width=800)
    assert result["id"] == 40
    assert result["character"] == 800


def test_clamp_ignores_unknown_columns_in_saved_widths():
    result = clamp_column_widths({"id": 60, "ghost_column": 999}, _COLUMNS)
    assert "ghost_column" not in result
