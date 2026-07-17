"""
_study.py — study-session logging (SQLite side of the SRS flow).

Split out of what used to be one large models.py. See database/models.py
for the public re-export facade.

Stage 1 of the clean-architecture migration moved the actual scheduling
math and the status state machine out of this file and into
domain/srs.py, which has no sqlite3 import and can be unit tested with no
database at all. This file now only does I/O: read the card's current
state, ask domain/srs.py what the new state should be, write it back.

The names below (_compute_srs_update, SRS_*) are re-exported unchanged so
database.models's public API — and every existing caller/test — keeps
working without any change.
"""
from ._common import get_connection, _db_op
from domain.srs import (
    compute_srs_update as _compute_srs_update,
    next_status,
    SRS_MAX_INTERVAL_DAYS,
    SRS_MIN_EASE,
    SRS_MAX_EASE,
    SRS_EASE_STEP,
    SRS_EASE_PENALTY,
    SRS_DEFAULT_EASE,
)


@_db_op
def log_study(card_id, result):
    conn = get_connection()
    conn.execute("INSERT INTO study_sessions (card_id,result) VALUES (?,?)", (card_id, result))

    row = conn.execute(
        "SELECT status, srs_interval, srs_ease FROM cards WHERE id=?", (card_id,)
    ).fetchone()
    current_status   = row["status"] if row else "new"
    current_interval = row["srs_interval"] if row else 1
    current_ease     = row["srs_ease"] if row else SRS_DEFAULT_EASE

    new_status = next_status(current_status, result)
    new_interval, new_ease = _compute_srs_update(current_interval, current_ease, result)

    conn.execute(
        "UPDATE cards SET status=?, srs_interval=?, srs_ease=?, "
        "srs_due_date=date('now','localtime', ?) WHERE id=?",
        (new_status, new_interval, new_ease, f"+{new_interval} day", card_id)
    )
    conn.commit()
