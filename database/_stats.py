"""
_stats.py — dashboard statistics.

Split out of what used to be one large models.py. See database/models.py
for the public re-export facade.
"""
from ._common import get_connection, _db_op


@_db_op
def get_stats():
    conn      = get_connection()
    cur       = conn.cursor()
    total     = cur.execute("SELECT COUNT(*) FROM cards WHERE deleted_at IS NULL").fetchone()[0]
    by_type   = dict(cur.execute("SELECT type, COUNT(*) FROM cards WHERE deleted_at IS NULL GROUP BY type").fetchall())
    by_status = dict(cur.execute("SELECT status, COUNT(*) FROM cards WHERE deleted_at IS NULL GROUP BY status").fetchall())
    favs      = cur.execute("SELECT COUNT(*) FROM cards WHERE is_favorite=1 AND deleted_at IS NULL").fetchone()[0]
    return {"total": total, "by_type": by_type, "by_status": by_status, "favorites": favs}


@_db_op
def get_full_stats():
    conn = get_connection()
    cur  = conn.cursor()

    total     = cur.execute("SELECT COUNT(*) FROM cards WHERE deleted_at IS NULL").fetchone()[0]
    by_type   = dict(cur.execute("SELECT type, COUNT(*) FROM cards WHERE deleted_at IS NULL GROUP BY type").fetchall())
    by_status = dict(cur.execute("SELECT status, COUNT(*) FROM cards WHERE deleted_at IS NULL GROUP BY status").fetchall())
    by_jlpt   = dict(cur.execute(
        "SELECT COALESCE(jlpt_level,'なし'), COUNT(*) FROM cards WHERE deleted_at IS NULL GROUP BY jlpt_level"
    ).fetchall())
    favorites = cur.execute("SELECT COUNT(*) FROM cards WHERE is_favorite=1 AND deleted_at IS NULL").fetchone()[0]

    daily_added = cur.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as n FROM cards
        WHERE created_at >= DATE('now','-30 days') AND deleted_at IS NULL
        GROUP BY day ORDER BY day
    """).fetchall()

    fields = ["reading_on","reading_kun","reading_kana","romaji",
              "meaning_vi","meaning_en","example_jp","example_vi",
              "stroke_count","jlpt_level","source","notes"]
    completeness = {}
    for f in fields:
        n = cur.execute(
            f"SELECT COUNT(*) FROM cards WHERE {f} IS NOT NULL AND {f}!='' AND deleted_at IS NULL"
        ).fetchone()[0]
        completeness[f] = round(n / total * 100) if total else 0

    sources    = cur.execute("""
        SELECT COALESCE(source,'(chưa có)'), COUNT(*) as n FROM cards
        WHERE deleted_at IS NULL GROUP BY source ORDER BY n DESC LIMIT 6
    """).fetchall()
    total_sessions = cur.execute("SELECT COUNT(*) FROM study_sessions").fetchone()[0]
    correct        = cur.execute("SELECT COUNT(*) FROM study_sessions WHERE result='correct'").fetchone()[0]
    daily_study    = cur.execute("""
        SELECT DATE(studied_at) as day, COUNT(*) as n FROM study_sessions
        WHERE studied_at >= DATE('now','-30 days') GROUP BY day ORDER BY day
    """).fetchall()
    deck_sizes = cur.execute("""
        SELECT d.name, COUNT(dc.card_id) as n FROM decks d
        LEFT JOIN deck_cards dc ON d.id=dc.deck_id GROUP BY d.id ORDER BY n DESC
    """).fetchall()
    return {
        "total": total, "by_type": by_type, "by_status": by_status,
        "by_jlpt": by_jlpt, "favorites": favorites,
        "daily_added":   [(r[0], r[1]) for r in daily_added],
        "completeness":  completeness,
        "sources":       [(r[0], r[1]) for r in sources],
        "total_sessions": total_sessions, "correct_sessions": correct,
        "daily_study":   [(r[0], r[1]) for r in daily_study],
        "deck_sizes":    [(r[0], r[1]) for r in deck_sizes],
    }
