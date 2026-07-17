"""
_decks.py — deck CRUD, deck-category CRUD, and card-to-deck assignment.

Split out of what used to be one large models.py. See database/models.py
for the public re-export facade.
"""
from ._common import get_connection, _db_op


# ── DECK CATEGORIES (danh mục nhóm các bộ thẻ, vd "Sách Kanji" > "Kanji tập 1") ─

@_db_op
def get_all_categories():
    conn = get_connection()
    rows = conn.execute("""
        SELECT cat.*, COUNT(d.id) as deck_count
        FROM deck_categories cat LEFT JOIN decks d ON d.category_id = cat.id
        GROUP BY cat.id ORDER BY cat.sort_order, cat.created_at
    """).fetchall()
    return [dict(r) for r in rows]


@_db_op
def add_category(name, icon="🗂️"):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("INSERT INTO deck_categories (name, icon) VALUES (?,?)", (name, icon))
    new_id = cur.lastrowid
    conn.commit()
    return new_id


@_db_op
def update_category(category_id: int, name: str, icon: str):
    conn = get_connection()
    conn.execute("UPDATE deck_categories SET name=?, icon=? WHERE id=?",
                 (name, icon, category_id))
    conn.commit()


@_db_op
def delete_category(category_id: int):
    """Xóa danh mục — các bộ thẻ bên trong KHÔNG bị xóa, chỉ chuyển về
    trạng thái 'Chưa phân loại' (category_id = NULL)."""
    conn = get_connection()
    conn.execute("UPDATE decks SET category_id=NULL WHERE category_id=?", (category_id,))
    conn.execute("DELETE FROM deck_categories WHERE id=?", (category_id,))
    conn.commit()


# ── DECKS ─────────────────────────────────────────────────────────────────────

@_db_op
def get_all_decks():
    conn = get_connection()
    rows = conn.execute("""
        SELECT d.*, COUNT(dc.card_id) as card_count,
               cat.name as category_name, cat.icon as category_icon
        FROM decks d
        LEFT JOIN deck_cards dc ON d.id = dc.deck_id
        LEFT JOIN deck_categories cat ON d.category_id = cat.id
        GROUP BY d.id ORDER BY cat.sort_order, cat.id, d.created_at
    """).fetchall()
    return [dict(r) for r in rows]


@_db_op
def add_deck(name, description="", color="#4A90D9", icon="📁", category_id=None):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO decks (name,description,color,icon,category_id) VALUES (?,?,?,?,?)",
        (name, description, color, icon, category_id))
    new_id = cur.lastrowid
    conn.commit()
    return new_id


@_db_op
def update_deck(deck_id: int, name: str, description: str,
                color: str, icon: str, category_id=None):
    conn = get_connection()
    conn.execute(
        "UPDATE decks SET name=?, description=?, color=?, icon=?, category_id=? WHERE id=?",
        (name, description, color, icon, category_id, deck_id))
    conn.commit()


@_db_op
def delete_deck(deck_id):
    conn = get_connection()
    conn.execute("DELETE FROM decks WHERE id=?", (deck_id,))
    conn.commit()


@_db_op
def add_card_to_deck(deck_id, card_id):
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO deck_cards (deck_id,card_id) VALUES (?,?)",
                 (deck_id, card_id))
    conn.commit()


@_db_op
def remove_card_from_deck(deck_id, card_id):
    """Mirrors add_card_to_deck. Moved here from a raw connection query
    that used to live inline in ui/card_detail.py's DeckAssignDialog
    (the deck-membership checkbox dialog)."""
    conn = get_connection()
    conn.execute("DELETE FROM deck_cards WHERE deck_id=? AND card_id=?",
                 (deck_id, card_id))
    conn.commit()


@_db_op
def bulk_add_to_deck(deck_id, ids: list):
    """Add multiple cards to a deck at once. Cards already in the deck are
    left untouched (INSERT OR IGNORE), so this is safe to call repeatedly."""
    if not ids:
        return
    conn = get_connection()
    conn.executemany(
        "INSERT OR IGNORE INTO deck_cards (deck_id,card_id) VALUES (?,?)",
        [(deck_id, cid) for cid in ids]
    )
    conn.commit()


@_db_op
def get_decks_for_card(card_id: int):
    """Every deck a given card belongs to (a card can be in several).
    Moved here from a raw connection query that used to live inline in
    ui/card_detail.py — same SQL, now named and reusable through
    database.models like every other query in this module."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT d.id, d.name, d.icon FROM decks d "
        "JOIN deck_cards dc ON dc.deck_id = d.id "
        "WHERE dc.card_id = ? ORDER BY d.name",
        (card_id,)
    ).fetchall()
    return [dict(r) for r in rows]
