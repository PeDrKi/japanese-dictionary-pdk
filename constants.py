"""
constants.py — Single source of truth for all domain values.
Import from here instead of hardcoding strings across the codebase.
"""

# ── Card types ────────────────────────────────────────────────────────────────
TYPE_KANJI    = "kanji"
TYPE_HIRAGANA = "hiragana"
TYPE_KATAKANA = "katakana"
TYPE_VOCAB    = "vocab"

CARD_TYPES = [TYPE_VOCAB, TYPE_KANJI, TYPE_HIRAGANA, TYPE_KATAKANA]

TYPE_LABELS = {
    TYPE_KANJI:    "漢",
    TYPE_HIRAGANA: "ひ",
    TYPE_KATAKANA: "ア",
    TYPE_VOCAB:    "語",
}

TYPE_LABELS_FULL = {
    TYPE_KANJI:    "漢字",
    TYPE_HIRAGANA: "ひらがな",
    TYPE_KATAKANA: "カタカナ",
    TYPE_VOCAB:    "語彙",
}

# ── Card status ───────────────────────────────────────────────────────────────
STATUS_NEW      = "new"
STATUS_LEARNING = "learning"
STATUS_KNOWN    = "known"

CARD_STATUSES = [STATUS_NEW, STATUS_LEARNING, STATUS_KNOWN]

STATUS_COLORS = {
    STATUS_NEW:      "#6B8CFF",
    STATUS_LEARNING: "#F0B429",
    STATUS_KNOWN:    "#4ECB85",
}

STATUS_LABELS = {
    STATUS_NEW:      "Chưa học",
    STATUS_LEARNING: "Đang học",
    STATUS_KNOWN:    "Đã nhớ",
}

# ── Từ loại (áp dụng cho thẻ từ vựng) — mã giống bản web ─────────────────────
CARD_POS = ["noun", "verb", "verb1", "verb2", "verb3", "adj_i", "adj_na",
            "pronoun", "particle", "adverb", "conjunction", "interjection"]
POS_LABELS = {
    "noun":   "Danh từ",
    "verb":   "Động từ",
    "verb1":  "Động từ nhóm 1",
    "verb2":  "Động từ nhóm 2",
    "verb3":  "Động từ nhóm 3",
    "adj_i":  "Tính từ đuôi い",
    "adj_na": "Tính từ đuôi な",
    "pronoun": "Đại từ",
    "particle": "Trợ từ",
    "adverb": "Trạng từ",
    "conjunction": "Liên từ",
    "interjection": "Thán từ",
}
POS_SHORT = {"noun": "Danh từ", "verb": "Động từ", "verb1": "ĐT 1", "verb2": "ĐT 2", "verb3": "ĐT 3",
             "adj_i": "TT い", "adj_na": "TT な", "pronoun": "Đại từ", "particle": "Trợ từ",
             "adverb": "Trạng từ", "conjunction": "Liên từ", "interjection": "Thán từ"}

# ── JLPT levels ───────────────────────────────────────────────────────────────
JLPT_LEVELS      = ["N5", "N4", "N3", "N2", "N1"]
JLPT_LEVELS_OPT  = [""] + JLPT_LEVELS   # includes blank for "no level"

JLPT_COLORS = {
    "N5": "#4ECB85",
    "N4": "#3ECFCF",
    "N3": "#4A90D9",
    "N2": "#9B7FE8",
    "N1": "#E85D5D",
}

# ── Study results ─────────────────────────────────────────────────────────────
RESULT_CORRECT   = "correct"
RESULT_INCORRECT = "incorrect"

# ── UI colours ────────────────────────────────────────────────────────────────
COLOR_GOLD   = "#F0B429"
COLOR_TEAL   = "#3ECFCF"
COLOR_PURPLE = "#9B7FE8"
COLOR_GREEN  = "#4ECB85"
COLOR_RED    = "#E85D5D"
COLOR_BLUE   = "#4A90D9"

PALETTE = [COLOR_BLUE, COLOR_GREEN, COLOR_GOLD, COLOR_RED,
           COLOR_PURPLE, COLOR_TEAL, "#F97316", "#FF6B9D"]

# ── Default UI values ─────────────────────────────────────────────────────────
DEFAULT_PAGE_SIZE  = 20
PAGE_SIZE_OPTIONS  = [20, 50, 100, 200]

DEFAULT_DECK_COLOR = "#4A90D9"
DEFAULT_DECK_ICON  = "📁"

DECK_COLORS = [COLOR_TEAL, COLOR_GOLD, COLOR_RED, COLOR_PURPLE,
               COLOR_GREEN, COLOR_BLUE, "#FF6B9D"]
DECK_ICONS  = ["📁", "📚", "🌸", "🎌", "⭐", "🔥", "💎", "🎯"]

# ── Keyboard shortcuts ────────────────────────────────────────────────────────
KB_NEW_CARD    = "<Control-n>"
KB_SAVE        = "<Control-s>"
KB_FOCUS_SEARCH= "<Control-f>"
KB_ESCAPE      = "<Escape>"
KB_DELETE      = "<Delete>"
KB_SELECT_ALL  = "<Control-a>"
KB_REFRESH     = "<F5>"
KB_TOGGLE_KEYBOARD = "<F8>"
KB_TAB_TABLE    = "<Control-Key-1>"
KB_TAB_STATS    = "<Control-Key-2>"
KB_TAB_RADICALS = "<Control-Key-3>"
KB_TAB_GRAMMAR  = "<Control-Key-4>"
KB_TAB_CONJ     = "<Control-Key-5>"
KB_TAB_TRANS    = "<Control-Key-6>"
KB_REVIEW_TODAY = "<Control-r>"
KB_FLASHCARD    = "<F2>"
KB_QUIZ         = "<F3>"
KB_TYPING       = "<F4>"
KB_BACKUP       = "<Control-b>"
KB_SYNC         = "<F9>"
KB_HELP         = "<F1>"
KB_EDIT         = "<Return>"

# Bảng phím tắt hiển thị trong hộp thoại "Phím tắt" (F1): (nhóm, [(phím, mô tả), ...])
SHORTCUT_HELP = [
    ("Chung", [
        ("Ctrl + 1 / 2 / 3", "Chuyển tab Thư viện / Thống kê / Bộ thủ"),
        ("Ctrl + 4 / 5 / 6", "Chuyển tab Ngữ pháp / Chia động từ / Bản dịch"),
        ("Ctrl + N", "Thêm thẻ mới"),
        ("Ctrl + F", "Tìm kiếm"),
        ("F5", "Tải lại dữ liệu"),
        ("F1", "Mở bảng phím tắt này"),
    ]),
    ("Ôn tập & công cụ", [
        ("Ctrl + R", "Ôn tập hôm nay (thẻ đến hạn)"),
        ("F2 / F3 / F4", "Thẻ ghi nhớ / Quiz / Luyện gõ"),
        ("F8", "Bật/tắt bàn phím ảo tiếng Nhật"),
        ("F9", "Đồng bộ (Sync)"),
        ("Ctrl + B", "Backup"),
    ]),
    ("Bảng thẻ", [
        ("Enter / nhấp đúp", "Sửa thẻ đang chọn"),
        ("Delete", "Xóa thẻ đang chọn"),
        ("Ctrl + A", "Chọn tất cả"),
        ("PageUp / PageDown", "Trang trước / sau"),
    ]),
    ("Trong form & hộp thoại", [
        ("Ctrl + S", "Lưu thẻ (form thêm/sửa)"),
        ("Esc", "Đóng hộp thoại"),
    ]),
    ("Khi ôn tập", [
        ("Space / Enter", "Lật thẻ"),
        ("← / →", "Chưa nhớ / Đã nhớ"),
        ("1 – 4", "Chọn đáp án (Quiz)"),
    ]),
]

# ── Limits ────────────────────────────────────────────────────────────────────
MAX_CHARACTER_LEN  = 50
MAX_MEANING_LEN    = 200
MAX_READING_LEN    = 100
MAX_EXAMPLE_LEN    = 500
MAX_NOTES_LEN      = 1000
MAX_SOURCE_LEN     = 100

# ── Settings keys ─────────────────────────────────────────────────────────────
SETTING_THEME       = "theme"
SETTING_WINDOW_GEO  = "window_geo"
SETTING_WINDOW_X    = "window_x"
SETTING_WINDOW_Y    = "window_y"
SETTING_LAST_TAB    = "last_tab"
SETTING_PAGE_SIZE   = "page_size"
SETTING_DETAIL_PANEL= "detail_panel"
SETTING_COL_WIDTHS  = "column_widths"

# ── Bộ icon cho Bộ thẻ / Danh mục (giống bản web: ICON_GROUPS) ─────────────────
ICON_GROUPS = [
    ('Học tập', '📁 📚 📖 📘 📗 📙 📕 📓 📒 📝 ✏️ 🖊️ 🎓 🏫 🧠 💡 🔍 🗂️ 📌 📎 🔖 🧾 📊 🗒️ 🧮 🔤 🔠 🔡 🈁 🈯 🈳 🈶 🈚 🈸 🈺 🈷️ 🉐 🉑 🀄'),
    ('Nhật Bản', '🎌 🗾 🌸 🏯 ⛩️ 🗻 🍣 🍙 🍱 🍜 🍡 🍵 🎍 🎎 🎏 🎐 🎑 🎋 🎆 🎇 🧧 🎴 👘 🥋 🏮 🍶 🥢 🛕 🚄 🎭 🪷 🎨 ⛰️ 🐟 🦀 🌊'),
    ('Đồ ăn', '🍎 🍊 🍋 🍌 🍉 🍇 🍓 🍑 🍒 🍍 🥝 🍅 🥕 🌽 🥔 🍆 🥦 🍞 🧀 🥚 🍳 🥞 🍗 🍖 🍔 🍟 🍕 🌭 🥪 🌮 🍝 🍲 🍛 🍤 🍦 🍩 🍪 🎂 🍰 🍫 🍬 ☕ 🥛 🍺 🍷 🧃'),
    ('Thiên nhiên', '🌳 🌲 🌴 🌵 🌿 🍀 🍁 🍂 🍃 🌺 🌻 🌼 🌷 🌹 💐 🌾 ☀️ 🌙 ⭐ 🌟 ☁️ ⛅ 🌧️ ⛈️ ❄️ ☃️ 🌈 💧 🔥 🌍 🏔️ 🏖️ 🌋'),
    ('Động vật', '🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🦆 🦉 🐺 🐴 🦄 🐝 🦋 🐌 🐞 🐢 🐍 🐙 🐠 🐬 🐳 🦈 🐘 🦒 🐇 🐿️'),
    ('Con người', '👤 👥 👨 👩 🧑 👶 👴 👵 🙂 😀 😊 😍 🤔 😴 😭 😡 💪 👀 👂 👃 👄 🖐️ 👍 🙏 ❤️ 🦷 🦴 🧍 🏃 🚶 👋 ✋ 🤝'),
    ('Nhà & đời sống', '🏠 🏢 🏥 🏦 🏪 🛒 🛏️ 🚪 🪑 🛁 🚿 🧹 🧺 👕 👗 👟 🎒 👜 👓 ⌚ 📱 💻 📷 🔑 💰 💳 ✉️ 📞 🕐 📅 🧴 🪥 🧼 💡'),
    ('Du lịch', '🚗 🚕 🚌 🚆 🚲 🛵 ✈️ 🚢 🚀 🗺️ 🧭 ⛽ 🏨 🎫 🛂 🧳 🌏 🏝️ ⛺ 🚉 🚏 🗼 🗽 🎡 🎢'),
    ('Công việc', '💼 🏭 🔧 🔨 ⚙️ 🧰 🖥️ ⌨️ 🖨️ 📈 📉 🗄️ 📋 📣 📢 ⚖️ 🔬 🧪 💊 ⚕️ 🩺 🏗️ 🚜 📦 🛠️'),
    ('Giải trí', '⚽ 🏀 🎾 🏐 ⛳ 🏊 🚴 🎮 🎲 🎯 🎵 🎶 🎤 🎧 🎸 🎹 🥁 🎬 📺 🧩 ♟️ 🎁 🎉 🎈 📻 🎻 🎺'),
    ('Biểu tượng', '⭐ 💎 🔥 ⚡ ❤️ 🧡 💛 💚 💙 💜 🖤 ✅ ❌ ❗ ❓ ♾️ 🔔 🔒 🏆 🥇 🎖️ 🚩 🔴 🟠 🟡 🟢 🔵 🟣 ⚫ ⚪ 🆕 🆗 🔰'),
]
ICON_GROUPS = [(name, icons.split()) for name, icons in ICON_GROUPS]
DECK_ICONS = [i for _, group in ICON_GROUPS for i in group]
