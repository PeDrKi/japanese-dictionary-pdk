import logging
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "japanese.db")

# Tách riêng để dùng lại được: sau khi migration UUIDv7 rebuild các bảng
# (rename→create→copy→drop), toàn bộ index cũ bị mất theo bảng gốc bị
# DROP, nên phải chạy lại đúng bộ CREATE INDEX này lần nữa sau migration.
_INDEX_DDL = """
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
    """


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


def init_db(seed_sample_data: bool = False, db_path: str | None = None):
    """
    Create the schema if it doesn't exist yet, and run any pending
    migrations. By default this does NOT insert the sample vocabulary —
    a fresh database (what a new install gets) starts empty.

    Pass seed_sample_data=True to also populate the 17-card demo set on
    an empty database — used by the test suite's fresh_db fixture, and
    can be used for a one-off "show me example data" setup, but is never
    the default so packaged/distributed builds don't ship pre-loaded
    with someone else's flashcards.

    Pass db_path để chạy schema + migration trên 1 file DB khác (không
    phải DB_PATH của app) — dùng bởi infrastructure/supabase_sync.py để
    đảm bảo file .db tải về từ Supabase luôn được nâng cấp lên đúng schema
    mới nhất TRƯỚC khi merge, phòng trường hợp bản trên Supabase là bản
    cũ (được upload từ 1 lần sync trước, lúc app chưa có các cột/migration
    mới nhất) — nếu không, merge sẽ báo lỗi kiểu "no such column: ...".
    """
    target_path = db_path or DB_PATH
    # Use a dedicated connection for init — never touches the thread-local pool
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS cards (
            id           TEXT PRIMARY KEY,
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
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            icon        TEXT DEFAULT '🗂️',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS decks (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            color       TEXT DEFAULT '#4A90D9',
            icon        TEXT DEFAULT '📁',
            category_id TEXT REFERENCES deck_categories(id),
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at  DATETIME
        );

        CREATE TABLE IF NOT EXISTS deck_cards (
            id         TEXT PRIMARY KEY,
            deck_id    TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            card_id    TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            added_at   DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at DATETIME,
            UNIQUE(deck_id, card_id)
        );

        -- Bộ thủ (radicals) do người dùng tự quản lý — KHÔNG tự sinh từ
        -- kanji_decomposition (xem README trong ui/radical_view.py). Người
        -- dùng tạo bộ, rồi kéo-thả thẻ Kanji/Từ vựng vào từng bộ.
        CREATE TABLE IF NOT EXISTS radicals (
            id          TEXT PRIMARY KEY,
            character   TEXT NOT NULL UNIQUE,
            name        TEXT,
            color       TEXT DEFAULT '#4A90D9',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at  DATETIME
        );

        CREATE TABLE IF NOT EXISTS radical_cards (
            id          TEXT PRIMARY KEY,
            radical_id  TEXT NOT NULL REFERENCES radicals(id) ON DELETE CASCADE,
            card_id     TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            added_at    DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at  DATETIME,
            UNIQUE(radical_id, card_id)
        );

        -- Người dùng tự định nghĩa cách tách bộ cho 1 chữ, ĐÈ LÊN dữ liệu
        -- IDS tự động (infrastructure/kanji_ids.py) cho riêng chữ đó. `parts`
        -- là chuỗi các ký tự thành phần viết liền nhau, VD "日音" nghĩa là
        -- 2 phần: 日 và 音 — xem application/decomposition_service.py.
        CREATE TABLE IF NOT EXISTS user_decompositions (
            character   TEXT PRIMARY KEY,
            parts       TEXT NOT NULL,
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at  DATETIME
        );

        CREATE TABLE IF NOT EXISTS study_sessions (
            id         TEXT PRIMARY KEY,
            card_id    TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            result     TEXT NOT NULL CHECK(result IN ('correct','incorrect')),
            studied_at DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        );

    """ + _INDEX_DDL)

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
    # ── Migrations for sync-safe soft-delete (updated_at/deleted_at trên
    #    decks/radicals/deck_cards/radical_cards, deleted_at trên
    #    user_decompositions) — cần để Supabase sync đồng bộ được việc xóa
    #    thay vì "hồi sinh" dữ liệu đã xóa khi merge với thiết bị khác.
    #
    #    Lưu ý: KHÔNG dùng "DEFAULT (datetime('now'))" trực tiếp trong ALTER
    #    TABLE ADD COLUMN — SQLite từ chối default không-hằng-số khi bảng
    #    đã có sẵn dữ liệu ("Cannot add a column with non-constant
    #    default"). Thêm cột rỗng trước, rồi backfill bằng UPDATE riêng.
    for alter_stmt, backfill_stmt in (
        ("ALTER TABLE decks ADD COLUMN updated_at DATETIME",
         "UPDATE decks SET updated_at = created_at WHERE updated_at IS NULL"),
        ("ALTER TABLE decks ADD COLUMN deleted_at DATETIME", None),
        ("ALTER TABLE radicals ADD COLUMN updated_at DATETIME",
         "UPDATE radicals SET updated_at = created_at WHERE updated_at IS NULL"),
        ("ALTER TABLE radicals ADD COLUMN deleted_at DATETIME", None),
        ("ALTER TABLE deck_cards ADD COLUMN updated_at DATETIME",
         "UPDATE deck_cards SET updated_at = added_at WHERE updated_at IS NULL"),
        ("ALTER TABLE deck_cards ADD COLUMN deleted_at DATETIME", None),
        ("ALTER TABLE radical_cards ADD COLUMN updated_at DATETIME",
         "UPDATE radical_cards SET updated_at = added_at WHERE updated_at IS NULL"),
        ("ALTER TABLE radical_cards ADD COLUMN deleted_at DATETIME", None),
        ("ALTER TABLE user_decompositions ADD COLUMN deleted_at DATETIME", None),
    ):
        try:
            cur.execute(alter_stmt)
        except Exception:
            pass  # Column already exists
        if backfill_stmt:
            try:
                cur.execute(backfill_stmt)
            except Exception:
                pass  # Column didn't exist before this run either — nothing to backfill

    # Index cần tạo SAU migration ở trên (DB cũ mới có cột category_id từ đây)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_decks_category ON decks(category_id)")

    # ── Migration ID: INTEGER AUTOINCREMENT → TEXT UUIDv7 ──
    # Tự phát hiện DB cũ (id còn kiểu INTEGER) và chuyển toàn bộ khoá
    # chính + khoá ngoại liên quan sang UUIDv7. Xem infrastructure/id_gen.py.
    _migrate_ids_to_uuid7(conn, cur)

    # Update query planner statistics after index changes
    conn.execute("PRAGMA optimize")
    conn.execute("ANALYZE")

    if seed_sample_data:
        count = cur.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        if count == 0:
            _insert_sample_data(cur)

    conn.commit()
    conn.close()


def _migrate_ids_to_uuid7(conn, cur):
    """
    Chuyển toàn bộ khoá chính INTEGER AUTOINCREMENT (cards, deck_categories,
    decks, deck_cards, radicals, radical_cards, study_sessions) sang TEXT
    UUIDv7 — để ID không bao giờ trùng giữa các thiết bị khi đồng bộ qua
    Supabase (xem infrastructure/id_gen.py để biết lý do chọn UUIDv7 thay
    vì UUIDv4 hay giữ nguyên số nguyên).

    An toàn để gọi ở MỌI lần init_db(): tự kiểm tra qua PRAGMA table_info
    xem cột `id` của bảng cards đã là TEXT (đã migrate) hay còn INTEGER
    (DB cũ, cần migrate) — nếu đã TEXT thì return ngay, không làm gì cả.

    user_decompositions không nằm trong danh sách này vì khoá chính của
    bảng đó vốn đã là `character` (TEXT), không phải id số.
    """
    info = cur.execute("PRAGMA table_info(cards)").fetchall()
    id_col = next((c for c in info if c["name"] == "id"), None)
    if id_col is None or id_col["type"].upper() == "TEXT":
        return  # Đã migrate từ trước, hoặc bảng chưa tồn tại (DB mới tinh)

    from infrastructure.id_gen import uuid7

    logging.info("Migrating database primary keys from INTEGER to UUIDv7...")
    # PRAGMA foreign_keys chỉ có tác dụng khi KHÔNG có transaction nào đang
    # mở — các câu UPDATE backfill chạy ngay trước đây (trong vòng lặp
    # ALTER TABLE ở trên) đã âm thầm mở 1 transaction, nên phải commit nó
    # lại trước, nếu không PRAGMA sau đây sẽ bị SQLite bỏ qua trong im
    # lặng và toàn bộ bước DROP TABLE bên dưới sẽ vướng ràng buộc khoá
    # ngoại giữa các bảng đang dở dang remap.
    conn.commit()
    cur.execute("PRAGMA foreign_keys = OFF")

    def build_map(table: str) -> dict:
        rows = cur.execute(f"SELECT id FROM {table}").fetchall()
        return {r["id"]: uuid7() for r in rows}

    cards_map    = build_map("cards")
    decks_map    = build_map("decks")
    cats_map     = build_map("deck_categories")
    radicals_map = build_map("radicals")

    def rebuild(table: str, create_sql: str, remap_row):
        """Đổi tên bảng cũ sang <table>_old, tạo bảng mới đúng schema TEXT,
        copy toàn bộ dữ liệu qua với id/khoá ngoại đã được remap, rồi xoá
        bảng cũ. `remap_row(dict) -> dict | None` — trả None để bỏ qua 1
        dòng (dùng cho FK mồ côi trỏ tới bản ghi không còn tồn tại)."""
        cur.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
        cur.execute(create_sql)
        old_rows = cur.execute(f"SELECT * FROM {table}_old").fetchall()
        new_rows = []
        skipped = 0
        for r in old_rows:
            mapped = remap_row(dict(r))
            if mapped is None:
                skipped += 1
                continue
            new_rows.append(mapped)
        if new_rows:
            cols = list(new_rows[0].keys())
            placeholders = ",".join("?" for _ in cols)
            cur.executemany(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                [tuple(row[c] for c in cols) for row in new_rows]
            )
        cur.execute(f"DROP TABLE {table}_old")
        if skipped:
            logging.warning(
                f"Migration {table}: bỏ qua {skipped} dòng có khoá ngoại "
                "mồ côi (trỏ tới bản ghi không còn tồn tại).")

    rebuild(
        "deck_categories",
        """CREATE TABLE deck_categories (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            icon        TEXT DEFAULT '🗂️',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        )""",
        lambda r: {**r, "id": cats_map[r["id"]]}
    )

    rebuild(
        "radicals",
        """CREATE TABLE radicals (
            id          TEXT PRIMARY KEY,
            character   TEXT NOT NULL UNIQUE,
            name        TEXT,
            color       TEXT DEFAULT '#4A90D9',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at  DATETIME
        )""",
        lambda r: {**r, "id": radicals_map[r["id"]]}
    )

    rebuild(
        "cards",
        """CREATE TABLE cards (
            id           TEXT PRIMARY KEY,
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
        )""",
        lambda r: {**r, "id": cards_map[r["id"]]}
    )

    def remap_deck(r):
        r = {**r, "id": decks_map[r["id"]]}
        cid = r.get("category_id")
        r["category_id"] = cats_map.get(cid) if cid is not None else None
        return r

    rebuild(
        "decks",
        """CREATE TABLE decks (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            color       TEXT DEFAULT '#4A90D9',
            icon        TEXT DEFAULT '📁',
            category_id TEXT REFERENCES deck_categories(id),
            created_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at  DATETIME
        )""",
        remap_deck
    )

    def remap_deck_card(r):
        deck_id = decks_map.get(r["deck_id"])
        card_id = cards_map.get(r["card_id"])
        if deck_id is None or card_id is None:
            return None  # FK mồ côi — deck hoặc card đã không còn tồn tại
        return {**r, "id": uuid7(), "deck_id": deck_id, "card_id": card_id}

    rebuild(
        "deck_cards",
        """CREATE TABLE deck_cards (
            id         TEXT PRIMARY KEY,
            deck_id    TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            card_id    TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            added_at   DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at DATETIME,
            UNIQUE(deck_id, card_id)
        )""",
        remap_deck_card
    )

    def remap_radical_card(r):
        radical_id = radicals_map.get(r["radical_id"])
        card_id    = cards_map.get(r["card_id"])
        if radical_id is None or card_id is None:
            return None
        return {**r, "id": uuid7(), "radical_id": radical_id, "card_id": card_id}

    rebuild(
        "radical_cards",
        """CREATE TABLE radical_cards (
            id          TEXT PRIMARY KEY,
            radical_id  TEXT NOT NULL REFERENCES radicals(id) ON DELETE CASCADE,
            card_id     TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            added_at    DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  DATETIME NOT NULL DEFAULT (datetime('now','localtime')),
            deleted_at  DATETIME,
            UNIQUE(radical_id, card_id)
        )""",
        remap_radical_card
    )

    def remap_study_session(r):
        card_id = cards_map.get(r["card_id"])
        if card_id is None:
            return None
        return {**r, "id": uuid7(), "card_id": card_id}

    rebuild(
        "study_sessions",
        """CREATE TABLE study_sessions (
            id         TEXT PRIMARY KEY,
            card_id    TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            result     TEXT NOT NULL CHECK(result IN ('correct','incorrect')),
            studied_at DATETIME NOT NULL DEFAULT (datetime('now','localtime'))
        )""",
        remap_study_session
    )

    cur.execute("PRAGMA foreign_keys = ON")

    # Toàn bộ index cũ đã mất theo các bảng bị DROP ở trên — tạo lại.
    cur.executescript(_INDEX_DDL)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_decks_category ON decks(category_id)")

    fk_errors = cur.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        logging.error(f"Migration UUIDv7: phát hiện {len(fk_errors)} lỗi khoá ngoại sau khi migrate")
    else:
        logging.info(
            f"Migration UUIDv7 hoàn tất: {len(cards_map)} thẻ, {len(decks_map)} deck, "
            f"{len(radicals_map)} bộ thủ đã được chuyển sang UUIDv7.")


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
    from infrastructure.id_gen import uuid7

    cur.executemany("""
        INSERT INTO cards (id,type,character,reading_on,reading_kun,reading_kana,
            romaji,meaning_vi,meaning_en,example_jp,example_vi,
            stroke_count,jlpt_level,status,is_favorite,audio_path,image_path)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [(uuid7(), *row) for row in cards])

    cur.execute("INSERT INTO decks (id,name,description,color,icon) VALUES (?,?,?,?,?)",
                (uuid7(),'Hiragana cơ bản','46 ký tự hiragana','#4ECDC4','🔵'))
    cur.execute("INSERT INTO decks (id,name,description,color,icon) VALUES (?,?,?,?,?)",
                (uuid7(),'Kanji N5','Kanji cấp độ N5','#F0B429','漢'))
    cur.execute("INSERT INTO decks (id,name,description,color,icon) VALUES (?,?,?,?,?)",
                (uuid7(),'Từ vựng hàng ngày','Từ dùng thường xuyên','#E85D5D','📝'))

    hid = cur.execute("SELECT id FROM decks WHERE name='Hiragana cơ bản'").fetchone()[0]
    kid = cur.execute("SELECT id FROM decks WHERE name='Kanji N5'").fetchone()[0]
    vid = cur.execute("SELECT id FROM decks WHERE name='Từ vựng hàng ngày'").fetchone()[0]

    for row in cur.execute("SELECT id FROM cards WHERE type='hiragana'").fetchall():
        cur.execute("INSERT OR IGNORE INTO deck_cards (id,deck_id,card_id) VALUES (?,?,?)",(uuid7(),hid,row[0]))
    for row in cur.execute("SELECT id FROM cards WHERE type='kanji'").fetchall():
        cur.execute("INSERT OR IGNORE INTO deck_cards (id,deck_id,card_id) VALUES (?,?,?)",(uuid7(),kid,row[0]))
    for row in cur.execute("SELECT id FROM cards WHERE type='vocab'").fetchall():
        cur.execute("INSERT OR IGNORE INTO deck_cards (id,deck_id,card_id) VALUES (?,?,?)",(uuid7(),vid,row[0]))
