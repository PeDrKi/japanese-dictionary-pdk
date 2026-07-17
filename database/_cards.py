"""
_cards.py — card CRUD, listing/search/filter, and bulk operations.

Split out of what used to be one large models.py. See database/models.py
for the public re-export facade that keeps `models.add_card(...)` etc.
working unchanged for all existing callers.
"""
from datetime import datetime
from ._common import get_connection, _db_op, _CARD_LIST_COLS


# ── CARDS ─────────────────────────────────────────────────────────────────────

@_db_op
def get_all_cards(type_filter=None, jlpt_filter=None, status_filter=None,
                  favorite_only=False, deck_id=None, search=None,
                  include_deleted=False, due_only=False, limit=None, offset=0):
    conn   = get_connection()
    cur    = conn.cursor()
    params = []

    # Use specific columns (skip heavy unused fields like audio/image paths)
    query = f"SELECT {_CARD_LIST_COLS} FROM cards c"

    if deck_id:
        query += " JOIN deck_cards dc ON c.id = dc.card_id AND dc.deck_id = ?"
        params.append(deck_id)

    conds = []
    if not include_deleted:
        conds.append("(c.deleted_at IS NULL)")
    if type_filter:
        conds.append("c.type = ?");        params.append(type_filter)
    if jlpt_filter:
        conds.append("c.jlpt_level = ?");  params.append(jlpt_filter)
    if status_filter:
        conds.append("c.status = ?");      params.append(status_filter)
    if favorite_only:
        conds.append("c.is_favorite = 1")
    if due_only:
        conds.append("(c.srs_due_date IS NULL OR c.srs_due_date <= date('now','localtime'))")
    if search:
        tokens = search.strip().split()
        for tok in tokens:
            s = f"%{tok}%"
            # character: try prefix match first (uses index), fallback to LIKE
            conds.append(
                "(c.character = ? OR c.character LIKE ? "
                "OR c.meaning_vi LIKE ? OR c.meaning_en LIKE ? "
                "OR c.romaji LIKE ? OR c.reading_kana LIKE ? "
                "OR c.reading_kun LIKE ? OR c.reading_on LIKE ? "
                "OR c.reading_hanviet LIKE ?)"
            )
            params.extend([tok, s, s, s, s, s, s, s, s])

    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY c.created_at DESC"

    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    rows = [dict(r) for r in cur.execute(query, params).fetchall()]
    return rows


@_db_op
def count_cards(type_filter=None, jlpt_filter=None, status_filter=None,
                favorite_only=False, deck_id=None, search=None, due_only=False):
    """Return total count matching filters (for pagination)."""
    conn   = get_connection()
    cur    = conn.cursor()
    query  = "SELECT COUNT(*) FROM cards c"
    params = []

    if deck_id:
        query += " JOIN deck_cards dc ON c.id = dc.card_id AND dc.deck_id = ?"
        params.append(deck_id)

    conds = ["(c.deleted_at IS NULL)"]
    if type_filter:
        conds.append("c.type = ?");       params.append(type_filter)
    if jlpt_filter:
        conds.append("c.jlpt_level = ?"); params.append(jlpt_filter)
    if status_filter:
        conds.append("c.status = ?");     params.append(status_filter)
    if favorite_only:
        conds.append("c.is_favorite = 1")
    if due_only:
        conds.append("(c.srs_due_date IS NULL OR c.srs_due_date <= date('now','localtime'))")
    if search:
        tokens = search.strip().split()
        for tok in tokens:
            s = f"%{tok}%"
            conds.append(
                "(c.character = ? OR c.character LIKE ? "
                "OR c.meaning_vi LIKE ? OR c.meaning_en LIKE ? "
                "OR c.romaji LIKE ? OR c.reading_kana LIKE ? "
                "OR c.reading_kun LIKE ? OR c.reading_on LIKE ? "
                "OR c.reading_hanviet LIKE ?)"
            )
            params.extend([tok, s, s, s, s, s, s, s, s])

    if conds:
        query += " WHERE " + " AND ".join(conds)

    n = cur.execute(query, params).fetchone()[0]
    return n


@_db_op
def get_due_count():
    """Number of non-deleted cards due for SRS review today (or never studied)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM cards WHERE deleted_at IS NULL "
        "AND (srs_due_date IS NULL OR srs_due_date <= date('now','localtime'))"
    ).fetchone()
    return row[0]


@_db_op
def get_card_by_id(card_id):
    conn = get_connection()
    row  = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    return dict(row) if row else None


@_db_op
def add_card(data: dict):
    conn = get_connection()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO cards (type,character,reading_on,reading_kun,reading_kana,reading_hanviet,
            romaji,meaning_vi,meaning_en,example_jp,example_vi,
            stroke_count,jlpt_level,status,is_favorite,source,notes,
            audio_path,image_path,created_at,updated_at)
        VALUES (:type,:character,:reading_on,:reading_kun,:reading_kana,:reading_hanviet,
            :romaji,:meaning_vi,:meaning_en,:example_jp,:example_vi,
            :stroke_count,:jlpt_level,:status,:is_favorite,:source,:notes,
            :audio_path,:image_path,:created_at,:updated_at)
    """, {"reading_hanviet": None, **data, "created_at": now, "updated_at": now})
    new_id = cur.lastrowid
    conn.commit()
    return new_id


@_db_op
def update_card(card_id, data: dict):
    conn = get_connection()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE cards SET
            type=:type, character=:character, reading_on=:reading_on,
            reading_kun=:reading_kun, reading_kana=:reading_kana,
            reading_hanviet=:reading_hanviet,
            romaji=:romaji, meaning_vi=:meaning_vi, meaning_en=:meaning_en,
            example_jp=:example_jp, example_vi=:example_vi,
            stroke_count=:stroke_count, jlpt_level=:jlpt_level,
            status=:status, is_favorite=:is_favorite, source=:source,
            notes=:notes, updated_at=:updated_at
        WHERE id=:id
    """, {"reading_hanviet": None, **data, "id": card_id, "updated_at": now})
    conn.commit()


@_db_op
def soft_delete_card(card_id: int):
    """Mark card as deleted (recoverable). Returns snapshot for undo."""
    conn = get_connection()
    row  = conn.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    if not row:
        return None
    snapshot = dict(row)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE cards SET deleted_at=? WHERE id=?", (now, card_id))
    conn.commit()
    return snapshot


@_db_op
def restore_card(card_id: int):
    """Restore a soft-deleted card."""
    conn = get_connection()
    conn.execute("UPDATE cards SET deleted_at=NULL WHERE id=?", (card_id,))
    conn.commit()


@_db_op
def hard_delete_card(card_id: int):
    """Permanently delete a card."""
    conn = get_connection()
    conn.execute("DELETE FROM cards WHERE id=?", (card_id,))
    conn.commit()


@_db_op
def get_deleted_cards():
    """Return all soft-deleted cards for the trash view."""
    conn  = get_connection()
    rows  = conn.execute(
        "SELECT * FROM cards WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@_db_op
def toggle_favorite(card_id):
    conn = get_connection()
    conn.execute("UPDATE cards SET is_favorite = 1 - is_favorite WHERE id=?", (card_id,))
    conn.commit()


# ── DUPLICATE CHECK ───────────────────────────────────────────────────────────

@_db_op
def find_duplicates(character: str, card_type: str, exclude_id: int = None):
    conn   = get_connection()
    q      = ("SELECT id,character,type,meaning_vi,jlpt_level FROM cards "
               "WHERE character=? AND type=? AND deleted_at IS NULL")
    params = [character.strip(), card_type]
    if exclude_id:
        q += " AND id != ?"
        params.append(exclude_id)
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    return rows


# ── BULK OPERATIONS ───────────────────────────────────────────────────────────

@_db_op
def bulk_update_status(ids: list, status: str):
    """Set status for multiple cards at once."""
    if not ids:
        return
    conn = get_connection()
    conn.execute(
        f"UPDATE cards SET status=? WHERE id IN ({','.join('?'*len(ids))})",
        [status] + list(ids)
    )
    conn.commit()


@_db_op
def bulk_toggle_favorite(ids: list):
    """Toggle is_favorite for multiple cards at once."""
    if not ids:
        return
    conn = get_connection()
    conn.execute(
        f"UPDATE cards SET is_favorite = 1 - is_favorite "
        f"WHERE id IN ({','.join('?'*len(ids))})",
        list(ids)
    )
    conn.commit()


@_db_op
def bulk_soft_delete(ids: list) -> list:
    """Soft-delete multiple cards. Returns list of snapshots for undo."""
    if not ids:
        return []
    conn  = get_connection()
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows  = conn.execute(
        f"SELECT * FROM cards WHERE id IN ({','.join('?'*len(ids))})",
        list(ids)
    ).fetchall()
    snapshots = [dict(r) for r in rows]
    conn.execute(
        f"UPDATE cards SET deleted_at=? WHERE id IN ({','.join('?'*len(ids))})",
        [now] + list(ids)
    )
    conn.commit()
    return snapshots
