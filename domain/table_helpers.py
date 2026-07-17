"""
domain/table_helpers.py — Pure (GUI-free) helpers extracted from
ui/table_view.py. Moved from utils/ (Stage: utils/ cleanup).

table_view.py handles a lot: rendering, selection, pagination, CSV import/
export, column-resize persistence... Pulling the sort comparator out here
keeps that file focused on Tk wiring, and lets the actual sorting logic be
unit tested directly (see tests/test_table_helpers.py) without spinning up
a CTk window.
"""

# Columns that should sort numerically (missing/None values sort last)
# rather than as text.
INT_COLS = {"id", "stroke_count"}


def sort_key(card: dict, col: str, int_cols: set = INT_COLS):
    """
    Sort key for a single card dict + column, matching TableView's
    original inline lambdas:
      - numeric columns: (is_missing, value_or_0) so blanks sort last
      - text columns:    lowercased string, case-insensitive
    """
    if col in int_cols:
        return (card.get(col) is None, card.get(col) or 0)
    return str(card.get(col) or "").lower()


def sort_cards(cards: list, col: str, ascending: bool = True, int_cols: set = INT_COLS) -> list:
    """
    Return a NEW list of card dicts sorted by `col` (does not mutate the
    input). Mirrors TableView._sort()'s behavior exactly.
    """
    return sorted(cards, key=lambda c: sort_key(c, col, int_cols), reverse=not ascending)


def clamp_column_widths(widths: dict, columns: list, min_width: int = 40, max_width: int = 800) -> dict:
    """
    Sanity-clamp saved column widths before applying them to the Treeview.
    Guards against corrupted/edited settings.json producing a 0-width or
    absurdly large column that makes the table unusable.
    `columns` is the COLUMNS list of (col_id, heading, default_width, stretch)
    tuples — used to fall back to the default width for unknown/invalid entries.
    """
    defaults = {cid: default_w for cid, _heading, default_w, *_ in columns}
    result = {}
    for cid, default_w in defaults.items():
        w = widths.get(cid, default_w)
        try:
            w = int(w)
        except (TypeError, ValueError):
            w = default_w
        result[cid] = max(min_width, min(max_width, w))
    return result
