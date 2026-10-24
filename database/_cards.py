"""
_cards.py — card CRUD, listing/search/filter, and bulk operations.

Split out of what used to be one large models.py. See database/models.py
for the public re-export facade that keeps `models.add_card(...)` etc.
working unchanged for all existing callers.
"""
from datetime import datetime
from ._common import get_connection, _db_op, _CARD_LIST_COLS
from infrastructure.id_gen import uuid7
from domain.srs import count_for_status, status_from_count


# ── CARDS ─────────────────────────────────────────────────────────────────────

@_db_op
def get_all_cards(type_filter=None, jlpt_filter=None, status_filter=None,
                  favorite_only=False, deck_id=None, search=None,
                  include_deleted=False, due_only=False, limit=None, offset=0, pos_filter=None):
    conn   = get_connection()
    cur    = conn.cursor()
    params = []

    # Use specific columns (skip heavy unused fields like audio/image paths)
    query = f"SELECT {_CARD_LIST_COLS} FROM cards c"

    if deck_id:
        query += " JOIN deck_cards dc ON c.id = dc.card_id AND dc.deck_id = ? AND dc.deleted_at IS NULL"
        params.append(deck_id)

    conds = []
    if not include_deleted:
        conds.append("(c.deleted_at IS NULL)")
    if type_filter:
        conds.append("c.type = ?");        params.append(type_filter)
    if jlpt_filter:
        conds.append("c.jlpt_level = ?");  params.append(jlpt_filter)
    if pos_filter:
        conds.append("c.pos = ?");         params.append(pos_filter)
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
                favorite_only=False, deck_id=None, search=None, due_only=False, pos_filter=None):
    """Return total count matching filters (for pagination)."""
    conn   = get_connection()
    cur    = conn.cursor()
    query  = "SELECT COUNT(*) FROM cards c"
    params = []

    if deck_id:
        query += " JOIN deck_cards dc ON c.id = dc.card_id AND dc.deck_id = ? AND dc.deleted_at IS NULL"
        params.append(deck_id)

    conds = ["(c.deleted_at IS NULL)"]
    if type_filter:
        conds.append("c.type = ?");       params.append(type_filter)
    if jlpt_filter:
        conds.append("c.jlpt_level = ?"); params.append(jlpt_filter)
    if pos_filter:
        conds.append("c.pos = ?");        params.append(pos_filter)
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
    """Thẻ mới: nếu dữ liệu mang trạng thái (CSV, thẻ mẫu…) thì suy ra số lần học tương ứng."""
    count = int(data["study_count"]) if data.get("study_count") is not None else count_for_status(data.get("status") or "new")
    conn = get_connection()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur  = conn.cursor()
    new_id = uuid7()
    cur.execute("""
        INSERT INTO cards (id,type,character,reading_on,reading_kun,reading_kana,reading_hanviet,
            romaji,meaning_vi,meaning_en,example_jp,example_vi,
            stroke_count,jlpt_level,status,study_count,is_favorite,source,notes,pos,
            audio_path,image_path,created_at,updated_at)
        VALUES (:id,:type,:character,:reading_on,:reading_kun,:reading_kana,:reading_hanviet,
            :romaji,:meaning_vi,:meaning_en,:example_jp,:example_vi,
            :stroke_count,:jlpt_level,:status,:study_count,:is_favorite,:source,:notes,:pos,
            :audio_path,:image_path,:created_at,:updated_at)
    """, {"reading_hanviet": None, "pos": None, **data, "id": new_id, "created_at": now, "updated_at": now,
          "study_count": count, "status": status_from_count(count)})
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
            is_favorite=:is_favorite, source=:source,
            notes=:notes, pos=:pos, updated_at=:updated_at
        WHERE id=:id
    """, {"reading_hanviet": None, "pos": None, **data, "id": card_id, "updated_at": now})
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
    conn.execute("UPDATE cards SET deleted_at=?, updated_at=? WHERE id=?", (now, now, card_id))
    conn.commit()
    return snapshot


@_db_op
def restore_card(card_id: int):
    """Restore a soft-deleted card."""
    conn = get_connection()
    conn.execute("UPDATE cards SET deleted_at=NULL, updated_at=datetime('now','localtime') WHERE id=?", (card_id,))
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
    conn.execute("UPDATE cards SET is_favorite = 1 - is_favorite, updated_at=datetime('now','localtime') WHERE id=?", (card_id,))
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
    """Đặt trạng thái cho nhiều thẻ: quy ra số lần học (chưa học 0 · đang học 1 · đã nhớ 20) để trạng thái luôn khớp số lần học."""
    if not ids:
        return
    conn = get_connection()
    for cid in ids:
        row = conn.execute("SELECT study_count FROM cards WHERE id=?", (cid,)).fetchone()
        n = count_for_status(status, row[0] if row else 0)
        conn.execute("UPDATE cards SET study_count=?, status=?, updated_at=datetime('now','localtime') WHERE id=?",
                     (n, status_from_count(n), cid))
    conn.commit()


@_db_op
def bulk_toggle_favorite(ids: list):
    """Đặt/bỏ yêu thích cho nhiều thẻ (cả nhóm cùng một trạng thái)."""
    if not ids:
        return
    conn = get_connection()
    ph = ','.join('?' * len(ids))
    # Giống bản web: chọn lẫn lộn → đặt TẤT CẢ là yêu thích; chọn toàn thẻ đã yêu thích → bỏ hết
    all_fav = conn.execute(f"SELECT COUNT(*)=0 FROM cards WHERE id IN ({ph}) AND is_favorite=0", list(ids)).fetchone()[0]
    conn.execute(
        f"UPDATE cards SET is_favorite = ?, updated_at=datetime('now','localtime') WHERE id IN ({ph})",
        [0 if all_fav else 1] + list(ids)
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
        f"UPDATE cards SET deleted_at=?, updated_at=? WHERE id IN ({','.join('?'*len(ids))})",
        [now, now] + list(ids)
    )
    conn.commit()
    return snapshots
