import customtkinter as ctk
import tkinter as tk
import logging
from constants import (
    CARD_TYPES, CARD_STATUSES, JLPT_LEVELS, JLPT_LEVELS_OPT,
    TYPE_LABELS, TYPE_LABELS_FULL, STATUS_COLORS, STATUS_LABELS,
    JLPT_COLORS, PALETTE, COLOR_GOLD, COLOR_RED, COLOR_GREEN,
    COLOR_TEAL, COLOR_PURPLE, COLOR_BLUE,
    STATUS_NEW, STATUS_LEARNING, STATUS_KNOWN,
    TYPE_KANJI, TYPE_HIRAGANA, TYPE_KATAKANA, TYPE_VOCAB,
    RESULT_CORRECT, RESULT_INCORRECT,
    DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS,
    MAX_CHARACTER_LEN, MAX_MEANING_LEN, MAX_READING_LEN,
    MAX_EXAMPLE_LEN, MAX_NOTES_LEN, MAX_SOURCE_LEN,
    KB_NEW_CARD, KB_SAVE, KB_FOCUS_SEARCH, KB_ESCAPE,
    KB_DELETE, KB_SELECT_ALL, KB_REFRESH,
    SETTING_COL_WIDTHS,
)

logger = logging.getLogger(__name__)


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, card_service, deck_service, stats_service, on_select_callback, **kwargs):
        super().__init__(master, width=220, corner_radius=0, **kwargs)
        self._card_service  = card_service
        self._deck_service  = deck_service
        self._stats_service = stats_service
        self.on_select    = on_select_callback
        self.selected_btn = None
        self._default_btn = None          # remember to activate after table is ready
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.pack_propagate(False)

        # Title
        title = ctk.CTkFrame(self, fg_color="transparent")
        title.pack(fill="x", padx=16, pady=(20,4))
        ctk.CTkLabel(title, text="🇯🇵", font=ctk.CTkFont(size=28)).pack(side="left")
        ctk.CTkLabel(title, text="  日本語\n  Học Tiếng Nhật",
                     font=ctk.CTkFont(size=12, weight="bold"), justify="left").pack(side="left")

        self._divider()

        # Library section
        self._section_label("📚 THƯ VIỆN")
        self._nav_btn("🗂️  Tất cả",   ("all",      None), is_default=True)
        self._nav_btn("⭐  Yêu thích", ("favorite", None))
        self._nav_btn("🆕  Mới thêm",  ("new_status",None))

        self._divider()

        # Type section
        self._section_label("🔤 LOẠI KÝ TỰ")
        self._nav_btn("　漢　Kanji",    ("type","kanji"))
        self._nav_btn("　ひ　Hiragana", ("type","hiragana"))
        self._nav_btn("　ア　Katakana", ("type","katakana"))
        self._nav_btn("　語　Từ vựng",  ("type","vocab"))

        self._divider()

        # Deck section header
        deck_hdr = ctk.CTkFrame(self, fg_color="transparent")
        deck_hdr.pack(fill="x", padx=12, pady=(0,4))
        ctk.CTkLabel(deck_hdr, text="📁 BỘ THẺ",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("gray50","gray60")).pack(side="left")
        ctk.CTkButton(deck_hdr, text="＋", width=24, height=24,
                      font=ctk.CTkFont(size=14), fg_color="transparent",
                      hover_color=("gray75","gray35"),
                      command=self._open_add_menu).pack(side="right")

        self.deck_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", height=220)
        self.deck_scroll.pack(fill="x", padx=4)
        self._collapsed_categories = set()   # id các danh mục đang thu gọn
        self.refresh_decks()

        # Spacer
        ctk.CTkFrame(self, fg_color="transparent").pack(fill="both", expand=True)

        # Stats
        stats_frame = ctk.CTkFrame(self, fg_color=("gray88","gray22"), corner_radius=8)
        stats_frame.pack(fill="x", padx=12, pady=(0,16))
        self.stats_label = ctk.CTkLabel(stats_frame, text="",
                                        font=ctk.CTkFont(size=11), justify="left")
        self.stats_label.pack(padx=12, pady=8, anchor="w")
        self.refresh_stats()

    def _divider(self):
        ctk.CTkFrame(self, height=1, fg_color=("gray80","gray30")).pack(fill="x", padx=12, pady=8)

    def _section_label(self, text):
        ctk.CTkLabel(self, text=text,
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("gray50","gray60"),
                     anchor="w").pack(fill="x", padx=16, pady=(0,2))

    def _nav_btn(self, label, filter_val, is_default=False):
        btn = ctk.CTkButton(
            self, text=label, anchor="w", height=34, corner_radius=6,
            fg_color="transparent", hover_color=("gray80","gray30"),
            text_color=("gray10","gray90"), font=ctk.CTkFont(size=13),
            command=lambda v=filter_val, b=None: self._select_later(v, b)
        )
        # Re-bind with actual btn reference after creation
        btn.configure(command=lambda v=filter_val, b=btn: self._select(v, b))
        btn.pack(fill="x", padx=8, pady=1)

        if is_default:
            self._default_btn     = btn
            self._default_filter  = filter_val

    # Called AFTER table is ready (from App)
    def activate_default(self):
        if self._default_btn:
            self._select(self._default_filter, self._default_btn)

    def _select(self, filter_val, btn):
        if self.selected_btn:
            self.selected_btn.configure(fg_color="transparent")
        btn.configure(fg_color=("gray75","gray35"))
        self.selected_btn = btn
        self.on_select(filter_val)

    # ── Decks & Danh mục ────────────────────────────────────────────────────────

    def _open_add_menu(self):
        """Nút "+" ở header BỘ THẺ → chọn thêm Danh mục hay thêm Bộ thẻ."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="🗂️  Thêm danh mục", command=self._open_add_category)
        menu.add_command(label="📁  Thêm bộ thẻ",   command=lambda: self._open_add_deck())
        try:
            x = self.winfo_pointerx(); y = self.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _open_add_deck(self, category_id=None):
        DeckDialog(self, self._deck_service, on_save=self._save_deck, default_category_id=category_id)

    def _save_deck(self, name, desc, color, icon, category_id):
        self._deck_service.add(name, desc, color, icon, category_id)
        self.refresh_decks()

    def _open_add_category(self):
        CategoryDialog(self, on_save=self._save_category)

    def _save_category(self, name, icon):
        self._deck_service.add_category(name, icon)
        self.refresh_decks()

    def refresh_decks(self):
        for w in self.deck_scroll.winfo_children():
            w.destroy()

        categories = self._deck_service.list_categories()
        decks      = self._deck_service.list_decks()

        by_cat = {}
        uncategorized = []
        for d in decks:
            if d.get("category_id"):
                by_cat.setdefault(d["category_id"], []).append(d)
            else:
                uncategorized.append(d)

        for cat in categories:
            self._render_category(cat, by_cat.get(cat["id"], []))

        if uncategorized:
            self._section_divider("— Chưa phân loại —")
            for deck in uncategorized:
                self._render_deck_row(deck, indent=8)

        if not categories and not decks:
            ctk.CTkLabel(
                self.deck_scroll, text="Chưa có bộ thẻ nào.\nBấm “＋” để tạo mới.",
                font=ctk.CTkFont(size=11), text_color=("gray55","gray55"),
                justify="left").pack(anchor="w", padx=8, pady=8)

    def _section_divider(self, text):
        ctk.CTkLabel(self.deck_scroll, text=text,
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("gray55","gray55")).pack(anchor="w", padx=8, pady=(6,2))

    # -- Danh mục (category) --------------------------------------------------

    def _render_category(self, cat: dict, decks_in_cat: list):
        collapsed = cat["id"] in self._collapsed_categories

        hdr = ctk.CTkFrame(self.deck_scroll, fg_color="transparent")
        hdr.pack(fill="x", pady=(4,0))

        arrow = "▸" if collapsed else "▾"
        toggle_btn = ctk.CTkButton(
            hdr, text=f"{arrow}  {cat['icon']}  {cat['name']}  ({cat['deck_count']})",
            anchor="w", height=28, corner_radius=6,
            fg_color="transparent", hover_color=("gray82","gray28"),
            text_color=("gray5","gray95"), font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda cid=cat["id"]: self._toggle_category(cid)
        )
        toggle_btn.pack(side="left", fill="x", expand=True)
        toggle_btn.bind("<Button-3>", lambda e, c=cat: self._category_context_menu(e, c))

        if not collapsed:
            for deck in decks_in_cat:
                self._render_deck_row(deck, indent=26)
            # Nút thêm bộ thẻ nhanh vào ngay danh mục này
            add_row = ctk.CTkButton(
                self.deck_scroll, text="＋ Thêm bộ thẻ vào đây",
                anchor="w", height=24, corner_radius=6,
                fg_color="transparent", hover_color=("gray85","gray25"),
                text_color=("gray45","gray60"), font=ctk.CTkFont(size=11),
                command=lambda cid=cat["id"]: self._open_add_deck(cid))
            add_row.pack(fill="x", padx=(26,4))

    def _toggle_category(self, category_id):
        if category_id in self._collapsed_categories:
            self._collapsed_categories.discard(category_id)
        else:
            self._collapsed_categories.add(category_id)
        self.refresh_decks()

    def _category_context_menu(self, event, cat: dict):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="✏️  Đổi tên / Sửa danh mục",
                         command=lambda: self._edit_category(cat))
        menu.add_command(label="📁  Thêm bộ thẻ vào đây",
                         command=lambda: self._open_add_deck(cat["id"]))
        menu.add_separator()
        menu.add_command(label="🗑️  Xóa danh mục (giữ lại bộ thẻ bên trong)",
                         command=lambda: self._delete_category(cat["id"]))
        menu.tk_popup(event.x_root, event.y_root)

    def _edit_category(self, cat: dict):
        CategoryDialog(self, category=cat, on_save=self._on_category_edited)

    def _on_category_edited(self, category_id, name, icon):
        self._deck_service.update_category(category_id, name, icon)
        self.refresh_decks()

    def _delete_category(self, category_id):
        self._deck_service.delete_category(category_id)
        self.refresh_decks()

    # -- Bộ thẻ (deck) ----------------------------------------------------------

    def _render_deck_row(self, deck: dict, indent: int = 8):
        row = ctk.CTkFrame(self.deck_scroll, fg_color="transparent")
        row.pack(fill="x", pady=1, padx=(indent, 0))
        btn = ctk.CTkButton(
            row,
            text=f"{deck['icon']}  {deck['name']}  ({deck['card_count']})",
            anchor="w", height=30, corner_radius=6,
            fg_color="transparent", hover_color=("gray80","gray30"),
            text_color=("gray10","gray90"), font=ctk.CTkFont(size=12),
            command=lambda d=deck: self.on_select(("deck", d["id"]))
        )
        btn.pack(side="left", fill="x", expand=True)
        btn.bind("<Button-3>", lambda e, d=deck: self._deck_context_menu(e, d))

        ctk.CTkButton(
            row, text="✕", width=22, height=22,
            fg_color="transparent", hover_color=("gray80","gray30"),
            text_color=("gray50","gray50"), font=ctk.CTkFont(size=11),
            command=lambda did=deck["id"]: self._delete_deck(did)
        ).pack(side="right", padx=2)

    def _delete_deck(self, deck_id):
        self._deck_service.delete(deck_id)
        self.refresh_decks()

    def _deck_context_menu(self, event, deck: dict):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="✏️  Đổi tên / Sửa",
                         command=lambda: self._edit_deck(deck))
        menu.add_separator()
        menu.add_command(label="🗑️  Xóa deck",
                         command=lambda: self._delete_deck(deck["id"]))
        menu.tk_popup(event.x_root, event.y_root)

    def _edit_deck(self, deck: dict):
        EditDeckDialog(self, self._deck_service, deck=deck, on_save=self._on_deck_edited)

    def _on_deck_edited(self, deck_id, name, desc, color, icon, category_id):
        self._deck_service.update(deck_id, name, desc, color, icon, category_id)
        self.refresh_decks()

    # ── Stats ──────────────────────────────────────────────────────────────────

    def refresh_stats(self, force=True):
        """Refresh stats label. Uses lightweight query."""
        if not force and getattr(self, "_stats_dirty", True) is False:
            return
        try:
            s = self._stats_service.get_summary()
            due = self._card_service.due_count()
            self.stats_label.configure(
                text=f"📊 Tổng: {s['total']} thẻ\n"
                     f"⭐ Yêu thích: {s['favorites']}\n"
                     f"✅ Đã nhớ: {s['by_status'].get('known', 0)}\n"
                     f"🎯 Cần ôn hôm nay: {due}")
            self._stats_dirty = False
        except Exception as e:
            logger.debug(f"Sidebar stats refresh failed: {e}")


# ── Deck dialog ────────────────────────────────────────────────────────────────

class DeckDialog(ctk.CTkToplevel):
    COLORS = ["#4ECDC4","#F0B429","#E85D5D","#9B7FE8","#4ECB85","#4A90D9","#FF6B9D"]
    ICONS  = ["📁","📚","🌸","🎌","⭐","🔥","💎","🎯"]

    def __init__(self, master, deck_service, on_save, default_category_id=None):
        super().__init__(master)
        self._deck_service = deck_service
        self.on_save = on_save
        self.title("Thêm Bộ Thẻ Mới")
        self.geometry("360x420")
        self.minsize(360, 380)
        self.resizable(True, True)
        self.grab_set()
        self.lift(); self.focus_force()

        # id -> "icon  Tên" cho dropdown; "" nghĩa là không chọn danh mục
        self._categories = self._deck_service.list_categories()
        self._cat_labels = ["— Không thuộc danh mục —"] + [
            f"{c['icon']}  {c['name']}" for c in self._categories
        ]
        self._default_category_id = default_category_id
        self._build()

    def _build(self):
        p = {"padx":20, "pady":6}
        ctk.CTkLabel(self, text="Tên bộ thẻ *", font=ctk.CTkFont(weight="bold")).pack(anchor="w",**p)
        self.name_entry = ctk.CTkEntry(self, placeholder_text="VD: Kanji N4")
        self.name_entry.pack(fill="x", **p)

        ctk.CTkLabel(self, text="Mô tả").pack(anchor="w", **p)
        self.desc_entry = ctk.CTkEntry(self, placeholder_text="Mô tả ngắn...")
        self.desc_entry.pack(fill="x", **p)

        ctk.CTkLabel(self, text="Danh mục").pack(anchor="w", **p)
        default_label = self._cat_labels[0]
        for c in self._categories:
            if c["id"] == self._default_category_id:
                default_label = f"{c['icon']}  {c['name']}"
        self.cat_var = ctk.StringVar(value=default_label)
        ctk.CTkOptionMenu(self, values=self._cat_labels,
                          variable=self.cat_var).pack(fill="x", padx=20)

        ctk.CTkLabel(self, text="Icon").pack(anchor="w", **p)
        icon_f = ctk.CTkFrame(self, fg_color="transparent")
        icon_f.pack(fill="x", padx=20)
        self.icon_var = ctk.StringVar(value=self.ICONS[0])
        for icon in self.ICONS:
            ctk.CTkRadioButton(icon_f, text=icon, variable=self.icon_var,
                               value=icon, width=44).pack(side="left", padx=1)

        ctk.CTkLabel(self, text="Màu sắc").pack(anchor="w", **p)
        color_f = ctk.CTkFrame(self, fg_color="transparent")
        color_f.pack(fill="x", padx=20)
        self.color_var = ctk.StringVar(value=self.COLORS[0])
        for c in self.COLORS:
            ctk.CTkRadioButton(color_f, text="●", variable=self.color_var,
                               value=c, text_color=c, width=32).pack(side="left", padx=1)

        ctk.CTkButton(self, text="💾  Lưu", command=self._save,
                      height=38).pack(fill="x", padx=20, pady=(16,8))

    def _selected_category_id(self):
        label = self.cat_var.get()
        for c in self._categories:
            if f"{c['icon']}  {c['name']}" == label:
                return c["id"]
        return None

    def _save(self):
        name = self.name_entry.get().strip()
        if name:
            self.on_save(name, self.desc_entry.get().strip(),
                         self.color_var.get(), self.icon_var.get(),
                         self._selected_category_id())
            self.destroy()


class EditDeckDialog(ctk.CTkToplevel):
    """Edit an existing deck's name, description, color, icon, and category."""

    COLORS = ["#4ECDC4","#F0B429","#E85D5D","#9B7FE8","#4ECB85","#4A90D9","#FF6B9D"]
    ICONS  = ["📁","📚","🌸","🎌","⭐","🔥","💎","🎯"]

    def __init__(self, master, deck_service, deck: dict, on_save):
        super().__init__(master)
        self._deck_service = deck_service
        self.deck    = deck
        self.on_save = on_save
        self.title("✏️  Sửa bộ thẻ")
        self.geometry("380x460")
        self.minsize(380, 420)
        self.resizable(True, True)
        self.grab_set()
        self.lift(); self.focus_force()

        self._categories = self._deck_service.list_categories()
        self._cat_labels = ["— Không thuộc danh mục —"] + [
            f"{c['icon']}  {c['name']}" for c in self._categories
        ]
        self._build()

    def _build(self):
        p = {"padx": 20, "pady": 6}

        ctk.CTkLabel(self, text="Tên bộ thẻ *",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", **p)
        self.name_entry = ctk.CTkEntry(self)
        self.name_entry.insert(0, self.deck.get("name", ""))
        self.name_entry.pack(fill="x", **p)

        ctk.CTkLabel(self, text="Mô tả").pack(anchor="w", **p)
        self.desc_entry = ctk.CTkEntry(self)
        self.desc_entry.insert(0, self.deck.get("description", "") or "")
        self.desc_entry.pack(fill="x", **p)

        ctk.CTkLabel(self, text="Danh mục").pack(anchor="w", **p)
        current_label = self._cat_labels[0]
        cur_cat_id = self.deck.get("category_id")
        for c in self._categories:
            if c["id"] == cur_cat_id:
                current_label = f"{c['icon']}  {c['name']}"
        self.cat_var = ctk.StringVar(value=current_label)
        ctk.CTkOptionMenu(self, values=self._cat_labels,
                          variable=self.cat_var).pack(fill="x", padx=20)

        ctk.CTkLabel(self, text="Icon").pack(anchor="w", **p)
        icon_f = ctk.CTkFrame(self, fg_color="transparent")
        icon_f.pack(fill="x", padx=20)
        self.icon_var = ctk.StringVar(value=self.deck.get("icon", "📁"))
        for icon in self.ICONS:
            ctk.CTkRadioButton(icon_f, text=icon, variable=self.icon_var,
                               value=icon, width=44).pack(side="left", padx=1)

        ctk.CTkLabel(self, text="Màu sắc").pack(anchor="w", **p)
        color_f = ctk.CTkFrame(self, fg_color="transparent")
        color_f.pack(fill="x", padx=20)
        self.color_var = ctk.StringVar(value=self.deck.get("color", self.COLORS[0]))
        for c in self.COLORS:
            ctk.CTkRadioButton(color_f, text="●", variable=self.color_var,
                               value=c, text_color=c, width=32).pack(side="left", padx=1)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkButton(btn_row, text="✕  Hủy",
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.destroy, width=100).pack(side="left")
        ctk.CTkButton(btn_row, text="💾  Lưu",
                      command=self._save, height=36).pack(side="right")

    def _selected_category_id(self):
        label = self.cat_var.get()
        for c in self._categories:
            if f"{c['icon']}  {c['name']}" == label:
                return c["id"]
        return None

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            return
        self.on_save(
            self.deck["id"],
            name,
            self.desc_entry.get().strip(),
            self.color_var.get(),
            self.icon_var.get(),
            self._selected_category_id(),
        )
        self.destroy()


# ── Category dialog ─────────────────────────────────────────────────────────────

class CategoryDialog(ctk.CTkToplevel):
    """Thêm mới hoặc sửa 1 Danh mục (nhóm các bộ thẻ lại với nhau)."""

    ICONS = ["🗂️","📘","📗","📙","📕","🐾","🎌","🍜","✈️","💼","🎨","⭐"]

    def __init__(self, master, on_save, category: dict = None):
        super().__init__(master)
        self.category = category
        self.on_save  = on_save
        self.title("✏️  Sửa danh mục" if category else "🗂️  Thêm danh mục mới")
        self.geometry("340x260")
        self.minsize(340, 240)
        self.resizable(True, True)
        self.grab_set()
        self.lift(); self.focus_force()
        self._build()

    def _build(self):
        p = {"padx": 20, "pady": 6}
        ctk.CTkLabel(self, text="Tên danh mục *",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", **p)
        self.name_entry = ctk.CTkEntry(self, placeholder_text="VD: Sách Kanji")
        if self.category:
            self.name_entry.insert(0, self.category.get("name", ""))
        self.name_entry.pack(fill="x", **p)

        ctk.CTkLabel(self, text="Icon").pack(anchor="w", **p)
        icon_f = ctk.CTkFrame(self, fg_color="transparent")
        icon_f.pack(fill="x", padx=20)
        default_icon = self.category.get("icon", self.ICONS[0]) if self.category else self.ICONS[0]
        self.icon_var = ctk.StringVar(value=default_icon)
        for i, icon in enumerate(self.ICONS):
            ctk.CTkRadioButton(icon_f, text=icon, variable=self.icon_var,
                               value=icon, width=44
                               ).grid(row=i // 6, column=i % 6, padx=1, pady=2)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(20, 8))
        ctk.CTkButton(btn_row, text="✕  Hủy",
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.destroy, width=100).pack(side="left")
        ctk.CTkButton(btn_row, text="💾  Lưu",
                      command=self._save, height=36).pack(side="right")

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            return
        if self.category:
            self.on_save(self.category["id"], name, self.icon_var.get())
        else:
            self.on_save(name, self.icon_var.get())
        self.destroy()
