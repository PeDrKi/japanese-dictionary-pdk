"""
_user_decompositions.py — user-defined "chữ này gồm những bộ nào" entries.

Lets a person fully override (or supply from scratch, for a character the
bundled IDS dataset has no entry for) the breakdown application/
decomposition_service.py shows for a given character. One row per
character; `parts` is every component character concatenated
(e.g. "日音" = 2 parts, 日 and 音) — no IDS-operator syntax, since the
decomposition graph doesn't display operators anyway (see
ui/kanji_decomposition_dialog.py).
"""
from ._common import get_connection, _db_op


@_db_op
def get_user_decomposition(character: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT parts FROM user_decompositions WHERE character=?", (character,)
    ).fetchone()
    return row["parts"] if row else None


@_db_op
def set_user_decomposition(character: str, parts: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO user_decompositions (character,parts,updated_at) VALUES (?,?,datetime('now','localtime')) "
        "ON CONFLICT(character) DO UPDATE SET parts=excluded.parts, updated_at=excluded.updated_at",
        (character, parts))
    conn.commit()


@_db_op
def delete_user_decomposition(character: str):
    conn = get_connection()
    conn.execute("DELETE FROM user_decompositions WHERE character=?", (character,))
    conn.commit()


@_db_op
def get_all_user_decompositions():
    conn = get_connection()
    rows = conn.execute(
        "SELECT character, parts FROM user_decompositions ORDER BY character"
    ).fetchall()
    return [dict(r) for r in rows]
