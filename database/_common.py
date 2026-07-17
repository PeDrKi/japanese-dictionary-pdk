"""
_common.py — shared plumbing for the database layer: thread-local connection
pooling, the DBError exception, and the @_db_op decorator.

Split out of what used to be one large models.py so that _cards.py,
_decks.py, _stats.py, and _study.py can each import just this small,
stable base without depending on each other.
"""
import sqlite3
import logging
import threading
from functools import wraps
from .db import get_connection as _get_raw_conn

logger = logging.getLogger(__name__)

# ── Thread-local connection pool ──────────────────────────────────────────────
# Reuse one connection per thread instead of open/close per query
_local = threading.local()


def _is_conn_alive(conn) -> bool:
    """Check if a sqlite3 connection is still usable."""
    try:
        conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def get_connection():
    """
    Return a cached per-thread connection.
    Automatically reopens if the connection was closed externally
    (e.g. after init_db() called conn.close()).
    """
    conn = getattr(_local, "conn", None)
    if conn is None or not _is_conn_alive(conn):
        conn = _get_raw_conn()
        _local.conn = conn
    return conn


def close_thread_connection():
    """Call on thread exit to release the cached connection."""
    conn = getattr(_local, "conn", None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


# Specific columns for card list (avoids transferring unused blob fields)
_CARD_LIST_COLS = (
    "c.id, type, character, reading_on, reading_kun, reading_kana, reading_hanviet, romaji, "
    "meaning_vi, meaning_en, jlpt_level, status, is_favorite, source, "
    "created_at, example_jp, example_vi, stroke_count, "
    "srs_interval, srs_due_date, srs_ease, audio_path, image_path"
)

# All columns for full card detail
_CARD_ALL_COLS = "*"


# ── Error helper ──────────────────────────────────────────────────────────────

class DBError(Exception):
    """Raised when a database operation fails."""
    pass


def _db_op(fn):
    """Decorator: wrap any DB function with consistent error handling."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except sqlite3.Error as e:
            logger.error(f"DB error in {fn.__name__}: {e}")
            raise DBError(f"Lỗi database [{fn.__name__}]: {e}") from e
    return wrapper
