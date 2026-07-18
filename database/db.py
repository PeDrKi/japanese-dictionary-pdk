import logging
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "japanese.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Performance PRAGMAs
    conn.execute("PRAGMA foreign_keys  = ON")
    conn.execute("PRAGMA journal_mode  = WAL")        # concurrent reads + faster writes
    conn.execute("PRAGMA synchronous   = NORMAL")     # safe but faster than FULL
    conn.execute("PRAGMA cache_size    = -16000")     # 16MB page cache (was 8MB)
    conn.execute("PRAGMA temp_store    = MEMORY")     # temp tables in RAM
    conn.execute("PRAGMA mmap_size     = 134217728")  # 128MB memory-mapped I/O (was 64MB)
    conn.execute("PRAGMA optimize")                   # auto-update query planner stats
    conn.execute("PRAGMA locking_mode  = NORMAL")     # allow WAL readers
    return conn


def init_db(seed_sample_data: bool = False):
    """
    Create the schema if it doesn't exist yet, and run any pending
    migrations. By default this does NOT insert the sample vocabulary —
    a fresh database (what a new install gets) starts empty.

    Pass seed_sample_data=True to also populate the 17-card demo set on
    an empty database — used by the test suite's fresh_db fixture, and
    can be used for a one-off "show me example data" setup, but is never
    the default so packaged/distributed builds don't ship pre-loaded
    with someone else's flashcards.
    """
    # Use a dedicated connection for init — never touches the thread-local pool
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS cards (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            type         TEXT NOT NULL CHECK(type IN ('kanji','hiragana','katakana','vocab')),
            character    TEXT NOT NULL,
            reading_on   TEXT,
            reading_kun  TEXT,
            reading_kana TEXT,
            reading_hanviet TEXT,
            romaji       TEXT,
            meaning_vi   TEXT NOT NULL,
            meaning_en   TEXT,
            example_jp   TEXT,
            example_vi   TEXT,
            stroke_count INTEGER,
            jlpt_level   TEXT,
            status       TEXT NOT NULL DEFAULT 'new',
            is_favorite  INTEGER NOT NULL DEFAULT 0,
            source       TEXT,
            notes        TEXT,
            audio_path   TEXT,
            image_path   TEXT,
            srs_interval INTEGER NOT NULL DEFAULT 1,
            srs_ease     REAL NOT NULL DEFAULT 2.5,
            srs_due_date DATE,
            created_at   DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at   DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at   DATETIME
        );

        CREATE TABLE IF NOT EXISTS deck_categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            icon        TEXT DEFAULT '🗂️',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS decks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            color       TEXT DEFAULT '#4A90D9',
            icon        TEXT DEFAULT '📁',
            category_id INTEGER REFERENCES deck_categories(id),
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS deck_cards (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id  INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            card_id  INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            added_at DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(deck_id, card_id)
        );

        -- Bộ thủ (radicals) do người dùng tự quản lý — KHÔNG tự sinh từ
        -- kanji_decomposition (xem README trong ui/radical_view.py). Người
        -- dùng tạo bộ, rồi kéo-thả thẻ Kanji/Từ vựng vào từng bộ.
        CREATE TABLE IF NOT EXISTS radicals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            character   TEXT NOT NULL UNIQUE,
            name        TEXT,
            color       TEXT DEFAULT '#4A90D9',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS radical_cards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            radical_id  INTEGER NOT NULL REFERENCES radicals(id) ON DELETE CASCADE,
            card_id     INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            added_at    DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(radical_id, card_id)
        );

        -- Người dùng tự định nghĩa cách tách bộ cho 1 chữ, ĐÈ LÊN dữ liệu
        -- IDS tự động (infrastructure/kanji_ids.py) cho riêng chữ đó. `parts`
        -- là chuỗi các ký tự thành phần viết liền nhau, VD "日音" nghĩa là
        -- 2 phần: 日 và 音 — xem application/decomposition_service.py.
        CREATE TABLE IF NOT EXISTS user_decompositions (
            character   TEXT PRIMARY KEY,
            parts       TEXT NOT NULL,
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS study_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id    INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            result     TEXT NOT NULL CHECK(result IN ('correct','incorrect')),
            studied_at DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- ── Indexes for fast filtering & search ──────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_cards_type       ON cards(type);
        CREATE INDEX IF NOT EXISTS idx_cards_status     ON cards(status);
        CREATE INDEX IF NOT EXISTS idx_cards_jlpt       ON cards(jlpt_level);
        CREATE INDEX IF NOT EXISTS idx_cards_favorite   ON cards(is_favorite);
        CREATE INDEX IF NOT EXISTS idx_cards_character  ON cards(character);
        CREATE INDEX IF NOT EXISTS idx_cards_created    ON cards(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_dc_deck_id       ON deck_cards(deck_id);
        CREATE INDEX IF NOT EXISTS idx_dc_card_id       ON deck_cards(card_id);
        CREATE INDEX IF NOT EXISTS idx_radicals_sort    ON radicals(sort_order);
        CREATE INDEX IF NOT EXISTS idx_rc_radical_id    ON radical_cards(radical_id);
        CREATE INDEX IF NOT EXISTS idx_rc_card_id       ON radical_cards(card_id);
        CREATE INDEX IF NOT EXISTS idx_ss_card_id       ON study_sessions(card_id);
        CREATE INDEX IF NOT EXISTS idx_ss_studied_at    ON study_sessions(studied_at DESC);

        -- Covering indexes for common filter+sort combinations
        CREATE INDEX IF NOT EXISTS idx_cards_del_created
            ON cards(deleted_at, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cards_type_del
            ON cards(type, deleted_at, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cards_status_del
            ON cards(status, deleted_at, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cards_jlpt_del
            ON cards(jlpt_level, deleted_at, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cards_fav_del
            ON cards(is_favorite, deleted_at, created_at DESC);
    """)

    # ── Migrations (safe to run on existing DBs) ──
    try:
        cur.execute("ALTER TABLE cards ADD COLUMN deleted_at DATETIME")
    except Exception:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE cards ADD COLUMN srs_interval INTEGER NOT NULL DEFAULT 1")
    except Exception:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE cards ADD COLUMN srs_ease REAL NOT NULL DEFAULT 2.5")
    except Exception:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE cards ADD COLUMN srs_due_date DATE")
    except Exception:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE cards ADD COLUMN reading_hanviet TEXT")
    except Exception:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE decks ADD COLUMN category_id INTEGER REFERENCES deck_categories(id)")
    except Exception:
        pass  # Column already exists

    # Index cần tạo SAU migration ở trên (DB cũ mới có cột category_id từ đây)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_decks_category ON decks(category_id)")

    # Update query planner statistics after index changes
    conn.execute("PRAGMA optimize")
    conn.execute("ANALYZE")

    if seed_sample_data:
        count = cur.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        if count == 0:
            _insert_sample_data(cur)

    conn.commit()
    conn.close()


def check_integrity() -> tuple[bool, str]:
    """
    Run SQLite integrity check.
    Returns (ok: bool, message: str).
    Called on startup to catch corruption early.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if result == "ok":
            return True, "ok"
        return False, result
    except Exception as e:
        return False, str(e)


def check_and_repair() -> tuple[bool, str]:
    """
    Check integrity; if corrupt, attempt to move DB aside and start fresh.
    Returns (was_ok: bool, message: str).
    """
    ok, msg = check_integrity()
    if ok:
        return True, "ok"

    import shutil, datetime
    backup = DB_PATH + ".corrupt." + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        shutil.move(DB_PATH, backup)
        logging.warning(f"DB corrupt ({msg}) — moved to {backup}, starting fresh")
        return False, f"Database bị lỗi, đã backup sang:\n{backup}\n\nApp sẽ tạo database mới."
    except Exception as e:
        return False, f"Database bị lỗi và không thể backup: {e}"


def _insert_sample_data(cur):
    cards = [
        ('hiragana','あ',None,None,'a','a','Âm a','a',None,None,None,None,'new',0,None,None),
        ('hiragana','い',None,None,'i','i','Âm i','i',None,None,None,None,'new',0,None,None),
        ('hiragana','う',None,None,'u','u','Âm u','u',None,None,None,None,'new',0,None,None),
        ('hiragana','え',None,None,'e','e','Âm e','e',None,None,None,None,'new',0,None,None),
        ('hiragana','お',None,None,'o','o','Âm o','o',None,None,None,None,'new',0,None,None),
        ('katakana','ア',None,None,'a','a','Âm a','a',None,None,None,None,'new',0,None,None),
        ('katakana','イ',None,None,'i','i','Âm i','i',None,None,None,None,'new',0,None,None),
        ('katakana','ウ',None,None,'u','u','Âm u','u',None,None,None,None,'new',0,None,None),
        ('kanji','日','ニチ、ジツ','ひ、か',None,'nichi/hi','Mặt trời, ngày','sun/day','毎日勉強する','Học mỗi ngày',4,'N5','new',0,None,None),
        ('kanji','月','ゲツ、ガツ','つき',None,'getsu/tsuki','Mặt trăng, tháng','moon/month','月が綺麗だ','Trăng đẹp quá',4,'N5','new',0,None,None),
        ('kanji','火','カ','ひ',None,'ka/hi','Lửa','fire','火事が起きた','Đám cháy xảy ra',4,'N5','new',0,None,None),
        ('kanji','水','スイ','みず',None,'sui/mizu','Nước','water','水を飲む','Uống nước',4,'N5','new',1,None,None),
        ('kanji','山','サン','やま',None,'san/yama','Núi','mountain','富士山は高い','Núi Phú Sĩ cao',3,'N5','new',0,None,None),
        ('vocab','食べる',None,None,'たべる','taberu','Ăn','to eat','ご飯を食べる','Ăn cơm',None,'N5','learning',1,None,None),
        ('vocab','飲む',None,None,'のむ','nomu','Uống','to drink','お茶を飲む','Uống trà',None,'N5','learning',0,None,None),
        ('vocab','行く',None,None,'いく','iku','Đi','to go','学校に行く','Đi đến trường',None,'N5','known',0,None,None),
        ('vocab','学校',None,None,'がっこう','gakkou','Trường học','school','学校は楽しい','Trường học vui',None,'N5','known',1,None,None),
    ]
    cur.executemany("""
        INSERT INTO cards (type,character,reading_on,reading_kun,reading_kana,
            romaji,meaning_vi,meaning_en,example_jp,example_vi,
            stroke_count,jlpt_level,status,is_favorite,audio_path,image_path)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, cards)

    cur.execute("INSERT INTO decks (name,description,color,icon) VALUES (?,?,?,?)",
                ('Hiragana cơ bản','46 ký tự hiragana','#4ECDC4','🔵'))
    cur.execute("INSERT INTO decks (name,description,color,icon) VALUES (?,?,?,?)",
                ('Kanji N5','Kanji cấp độ N5','#F0B429','漢'))
    cur.execute("INSERT INTO decks (name,description,color,icon) VALUES (?,?,?,?)",
                ('Từ vựng hàng ngày','Từ dùng thường xuyên','#E85D5D','📝'))

    hid = cur.execute("SELECT id FROM decks WHERE name='Hiragana cơ bản'").fetchone()[0]
    kid = cur.execute("SELECT id FROM decks WHERE name='Kanji N5'").fetchone()[0]
    vid = cur.execute("SELECT id FROM decks WHERE name='Từ vựng hàng ngày'").fetchone()[0]

    for row in cur.execute("SELECT id FROM cards WHERE type='hiragana'").fetchall():
        cur.execute("INSERT OR IGNORE INTO deck_cards (deck_id,card_id) VALUES (?,?)",(hid,row[0]))
    for row in cur.execute("SELECT id FROM cards WHERE type='kanji'").fetchall():
        cur.execute("INSERT OR IGNORE INTO deck_cards (deck_id,card_id) VALUES (?,?)",(kid,row[0]))
    for row in cur.execute("SELECT id FROM cards WHERE type='vocab'").fetchall():
        cur.execute("INSERT OR IGNORE INTO deck_cards (deck_id,card_id) VALUES (?,?)",(vid,row[0]))
