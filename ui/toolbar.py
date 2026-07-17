"""
toolbar.py — Two-row toolbar: search+filters on row 0, actions on row 1.
Extracted from table_view.py.
"""
import customtkinter as ctk
import tkinter as tk
from constants import (
    CARD_TYPES, CARD_STATUSES, JLPT_LEVELS,
    KB_ESCAPE,
)
from ui.tooltip import Tooltip
import logging

logger = logging.getLogger(__name__)


class Toolbar(ctk.CTkFrame):
    """
    Two-row toolbar:
      Row 0 — Search box + JLPT filter + Status filter + "Lọc nâng cao" toggle
      Row 1 — Action buttons (Add, Import, Export CSV, Anki, Template, Trash, Detail)
    """

    def __init__(self, master,
                 on_search,
                 on_filter_change,
                 on_add,
                 on_quick_add,
                 on_import,
                 on_export,
                 on_export_anki,
                 on_template,
                 on_toggle_detail,
                 on_toggle_trash,
                 **kwargs):
        super().__init__(master, fg_color=("gray92", "gray18"),
                         corner_radius=0, **kwargs)
        self._on_search         = on_search
        self._on_filter_change  = on_filter_change
        self._on_add            = on_add
        self._on_quick_add      = on_quick_add
        self._on_import         = on_import
        self._on_export         = on_export
        self._on_export_anki    = on_export_anki
        self._on_template       = on_template
        self._on_toggle_detail  = on_toggle_detail
        self._on_toggle_trash   = on_toggle_trash
        self._adv_visible       = False
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Row 0: Search + Filters ──────────────────────────────────────────
        row0 = ctk.CTkFrame(self, fg_color="transparent", height=46)
        row0.pack(fill="x", padx=8, pady=(6, 0))
        row0.pack_propagate(False)

        # Search entry
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write",
            lambda *_: self._on_search(self._search_var.get()))
        self._search_entry = ctk.CTkEntry(
            row0,
            placeholder_text="🔍  Tìm ký tự, nghĩa, romaji...",
            textvariable=self._search_var,
            width=280, height=32)
        self._search_entry.pack(side="left", padx=(0, 8))
        self._search_entry.bind(KB_ESCAPE, lambda _: self._search_var.set(""))

        # JLPT
        self._jlpt_var = ctk.StringVar(value="Tất cả JLPT")
        ctk.CTkOptionMenu(
            row0, values=["Tất cả JLPT"] + JLPT_LEVELS,
            variable=self._jlpt_var, width=120, height=32,
            command=lambda _: self._on_filter_change()
        ).pack(side="left", padx=(0, 6))

        # Status
        self._status_var = ctk.StringVar(value="Tất cả")
        ctk.CTkOptionMenu(
            row0, values=["Tất cả"] + CARD_STATUSES,
            variable=self._status_var, width=120, height=32,
            command=lambda _: self._on_filter_change()
        ).pack(side="left", padx=(0, 6))

        # Advanced filter toggle (right side of row 0)
        self._adv_btn = ctk.CTkButton(
            row0, text="⚙  Lọc nâng cao", width=120, height=32,
            corner_radius=6,
            fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
            command=self.toggle_advanced_filter)
        self._adv_btn.pack(side="right", padx=(0, 4))
        Tooltip(self._adv_btn, "Lọc theo: loại ký tự, yêu thích, ví dụ, nguồn")

        # Detail panel toggle
        self._toggle_btn = ctk.CTkButton(
            row0, text="▶ Chi tiết", width=90, height=32,
            corner_radius=6,
            fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
            command=self._on_toggle_detail)
        self._toggle_btn.pack(side="right", padx=(0, 6))
        Tooltip(self._toggle_btn, "Ẩn/hiện panel chi tiết thẻ")

        # ── Row 1: Action buttons ─────────────────────────────────────────────
        row1 = ctk.CTkFrame(self, fg_color="transparent", height=42)
        row1.pack(fill="x", padx=8, pady=(4, 6))
        row1.pack_propagate(False)

        bk = dict(height=30, corner_radius=6)
        primary    = {}
        secondary  = dict(fg_color=("gray75","gray35"), text_color=("gray10","gray90"))

        actions = [
            ("➕  Thêm thẻ",    primary,   self._on_add,          "Thêm thẻ mới  (Ctrl+N)"),
            ("⚡  Nhập nhanh",  secondary, self._on_quick_add,    "Dán nhiều dòng \"chữ - nghĩa\", tạo nhiều thẻ cùng lúc"),
            ("📥  Import CSV",  secondary, self._on_import,       "Import thẻ từ file CSV"),
            ("📤  Export CSV",  secondary, self._on_export,       "Export thẻ hiện tại ra CSV"),
            ("🎴  Anki",        secondary, self._on_export_anki,  "Export sang Anki .apkg  (cần: pip install genanki)"),
            ("📋  Template",    secondary, self._on_template,     "Tải file CSV mẫu để điền rồi import"),
            ("🗑️  Thùng rác",  secondary, self._on_toggle_trash, "Xem và khôi phục thẻ đã xóa"),
        ]

        for text, style, cmd, tip in actions:
            btn = ctk.CTkButton(row1, text=text, command=cmd, **bk, **style)
            btn.pack(side="left", padx=(0, 6))
            Tooltip(btn, tip)

    # ── Advanced filter panel ─────────────────────────────────────────────────

    def build_advanced_panel(self, parent):
        """Build advanced filter bar — placed in parent by TableView."""
        self._adv_bar = ctk.CTkFrame(parent, fg_color=("gray88","gray22"),
                                      corner_radius=0, height=52)
        self._adv_bar.grid_columnconfigure(99, weight=1)
        pad = dict(padx=6, pady=10)

        ctk.CTkLabel(self._adv_bar, text="Loại:", font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")).grid(row=0, column=0, padx=(14,2), pady=10)
        self._adv_type = ctk.StringVar(value="Tất cả")
        ctk.CTkOptionMenu(self._adv_bar, values=["Tất cả"] + CARD_TYPES,
                          variable=self._adv_type, width=110,
                          command=lambda _: self._on_filter_change()
                          ).grid(row=0, column=1, **pad)

        ctk.CTkLabel(self._adv_bar, text="Yêu thích:", font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")).grid(row=0, column=2, padx=(8,2), pady=10)
        self._adv_fav = ctk.StringVar(value="Tất cả")
        ctk.CTkOptionMenu(self._adv_bar, values=["Tất cả","⭐ Chỉ yêu thích"],
                          variable=self._adv_fav, width=130,
                          command=lambda _: self._on_filter_change()
                          ).grid(row=0, column=3, **pad)

        ctk.CTkLabel(self._adv_bar, text="Có ví dụ:", font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")).grid(row=0, column=4, padx=(8,2), pady=10)
        self._adv_example = ctk.StringVar(value="Tất cả")
        ctk.CTkOptionMenu(self._adv_bar, values=["Tất cả","Có ví dụ","Chưa có ví dụ"],
                          variable=self._adv_example, width=130,
                          command=lambda _: self._on_filter_change()
                          ).grid(row=0, column=5, **pad)

        ctk.CTkLabel(self._adv_bar, text="Nguồn:", font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")).grid(row=0, column=6, padx=(8,2), pady=10)
        self._adv_source = ctk.StringVar()
        self._adv_source.trace_add("write", lambda *_: self._on_filter_change())
        ctk.CTkEntry(self._adv_bar, textvariable=self._adv_source,
                     placeholder_text="Tìm theo nguồn...",
                     width=150, height=32).grid(row=0, column=7, **pad)

        ctk.CTkButton(self._adv_bar, text="✕ Xoá bộ lọc", width=100, height=32,
                      corner_radius=6,
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.reset_advanced
                      ).grid(row=0, column=8, padx=(4,14), pady=10)

        return self._adv_bar

    def toggle_advanced_filter(self):
        self._adv_visible = not self._adv_visible
        if self._adv_visible:
            self._adv_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
            self._adv_btn.configure(
                text="⚙  Lọc nâng cao ✓",
                fg_color=("#3B82F6","#2563EB"), text_color="white")
        else:
            self._adv_bar.grid_remove()
            self._adv_btn.configure(
                text="⚙  Lọc nâng cao",
                fg_color=("gray75","gray35"), text_color=("gray10","gray90"))

    def reset_advanced(self):
        self._adv_type.set("Tất cả")
        self._adv_fav.set("Tất cả")
        self._adv_example.set("Tất cả")
        self._adv_source.set("")

    def set_detail_btn_text(self, visible: bool):
        self._toggle_btn.configure(
            text="▶ Chi tiết" if visible else "◀ Chi tiết")

    # ── Public getters ────────────────────────────────────────────────────────

    @property
    def search(self) -> str:
        return self._search_var.get().strip()

    @property
    def jlpt(self):
        v = self._jlpt_var.get()
        return None if "Tất cả" in v else v

    @property
    def status(self):
        v = self._status_var.get()
        return None if v == "Tất cả" else v

    @property
    def adv_type(self):
        v = getattr(self, "_adv_type", None)
        val = v.get() if v else "Tất cả"
        return None if val == "Tất cả" else val

    @property
    def adv_fav_only(self) -> bool:
        v = getattr(self, "_adv_fav", None)
        return v.get() == "⭐ Chỉ yêu thích" if v else False

    @property
    def adv_example(self) -> str:
        v = getattr(self, "_adv_example", None)
        return v.get() if v else "Tất cả"

    @property
    def adv_source(self) -> str:
        v = getattr(self, "_adv_source", None)
        return (v.get() or "").strip().lower() if v else ""

    def reset_filters(self):
        self._jlpt_var.set("Tất cả JLPT")
        self._status_var.set("Tất cả")

    def focus_search(self):
        self._search_entry.focus_set()
