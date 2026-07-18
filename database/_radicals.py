"""
_radicals.py — radical (bộ thủ) CRUD, and card-to-radical assignment.

Mirrors _decks.py's shape (radicals/radical_cards are structurally the
same idea as decks/deck_cards — a named group with a many-to-many link
to cards) but radicals have no categories and do have a user-controlled
sort_order, since the UI lets people drag to reorder their bộ list.

Deliberately NOT auto-populated from domain/kanji_decomposition.py — the
decomposition feature explains a kanji's *structure*, but which cards the
user considers to belong to a given bộ is their own call, entered/curated
by hand (see ui/radical_view.py).
"""
from ._common import get_connection, _db_op


@_db_op
def get_all_radicals():
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.*, COUNT(rc.card_id) as card_count
        FROM radicals r LEFT JOIN radical_cards rc ON rc.radical_id = r.id
        GROUP BY r.id ORDER BY r.sort_order, r.created_at
    """).fetchall()
    return [dict(r) for r in rows]


@_db_op
def add_radical(character: str, name: str = "", color: str = "#4A90D9"):
    conn = get_connection()
    cur  = conn.cursor()
    next_order = cur.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM radicals").fetchone()[0]
    cur.execute(
        "INSERT INTO radicals (character,name,color,sort_order) VALUES (?,?,?,?)",
        (character, name, color, next_order))
    new_id = cur.lastrowid
    conn.commit()
    return new_id


@_db_op
def update_radical(radical_id: int, character: str, name: str, color: str):
    conn = get_connection()
    conn.execute(
        "UPDATE radicals SET character=?, name=?, color=? WHERE id=?",
        (character, name, color, radical_id))
    conn.commit()


@_db_op
def delete_radical(radical_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM radicals WHERE id=?", (radical_id,))
    conn.commit()


@_db_op
def reorder_radicals(ordered_ids: list):
    """Persist a new drag-and-drop order for the radical list itself.
    `ordered_ids` is every radical id, in the desired display order."""
    conn = get_connection()
    conn.executemany(
        "UPDATE radicals SET sort_order=? WHERE id=?",
        [(i, rid) for i, rid in enumerate(ordered_ids)])
    conn.commit()


@_db_op
def add_card_to_radical(radical_id: int, card_id: int):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO radical_cards (radical_id,card_id) VALUES (?,?)",
                 (radical_id, card_id))
    conn.commit()


@_db_op
def remove_card_from_radical(radical_id: int, card_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM radical_cards WHERE radical_id=? AND card_id=?",
                 (radical_id, card_id))
    conn.commit()


@_db_op
def get_radicals_for_card(card_id: int):
    """Every bộ a given card has been placed in (a card can be in several)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT r.id, r.character, r.name, r.color FROM radicals r "
        "JOIN radical_cards rc ON rc.radical_id = r.id "
        "WHERE rc.card_id = ? ORDER BY r.sort_order",
        (card_id,)
    ).fetchall()
    return [dict(r) for r in rows]


@_db_op
def get_cards_for_radical(radical_id: int):
    """Every card placed in a given bộ — the "tra cứu 1 bộ gồm nhiều từ
    thuộc bộ đó" lookup. Excludes soft-deleted cards, same as the rest of
    the app's card lists."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT c.* FROM cards c "
        "JOIN radical_cards rc ON rc.card_id = c.id "
        "WHERE rc.radical_id = ? AND c.deleted_at IS NULL "
        "ORDER BY c.character",
        (radical_id,)
    ).fetchall()
    return [dict(r) for r in rows]
