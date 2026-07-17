import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
from database.models import DBError
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

TYPE_LABELS = {"kanji": "漢", "hiragana": "ひ", "katakana": "ア", "vocab": "語"}


class TrashView(ctk.CTkToplevel):
    """Shows soft-deleted cards and allows restore or permanent delete."""

    def __init__(self, master, card_service, on_restore=None):
        super().__init__(master)
        self._card_service = card_service
        self.on_restore = on_restore
        self.title("🗑️  Thùng rác")
        self.geometry("800x500")
        self.resizable(True, True)
        self.grab_set()
        self.lift(); self.focus_force()
        self._build()
        self.refresh()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        self.bind(KB_REFRESH, lambda _: self.refresh())

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top bar
        top = ctk.CTkFrame(self, fg_color=("gray90","gray18"),
                            corner_radius=0, height=50)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_propagate(False)
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="🗑️  Thùng rác — Thẻ đã xóa",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=0, column=0, padx=14, pady=12, sticky="w")

        btn_cfg = dict(height=32, corner_radius=6)
        ctk.CTkButton(top, text="↩️  Khôi phục đã chọn",
                      command=self._restore_selected, **btn_cfg
                      ).grid(row=0, column=1, padx=4, pady=9)
        ctk.CTkButton(top, text="🗑️  Xóa vĩnh viễn đã chọn",
                      fg_color="#c0392b", hover_color="#922b21", text_color="white",
                      command=self._hard_delete_selected, **btn_cfg
                      ).grid(row=0, column=2, padx=4, pady=9)
        ctk.CTkButton(top, text="💀  Dọn sạch thùng rác",
                      fg_color=("gray60","gray35"), text_color=("gray10","gray90"),
                      command=self._empty_trash, **btn_cfg
                      ).grid(row=0, column=3, padx=(4,14), pady=9)

        # Treeview
        tree_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        dark = ctk.get_appearance_mode() == "Dark"
        style.configure("Trash.Treeview",
            background="#1e2130" if dark else "#f5f5f5",
            foreground="#e8eaf0" if dark else "#1a1a2e",
            fieldbackground="#1e2130" if dark else "#f5f5f5",
            rowheight=28, font=("Segoe UI", 11))
        style.configure("Trash.Treeview.Heading",
            background="#161927" if dark else "#dde0e8",
            foreground="#e8eaf0" if dark else "#1a1a2e",
            font=("Segoe UI", 11, "bold"), relief="flat")

        cols = ["id","type","character","meaning_vi","jlpt_level","status","deleted_at"]
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  selectmode="extended", style="Trash.Treeview")
        heads = {"id":"ID","type":"Loại","character":"Ký tự","meaning_vi":"Nghĩa VN",
                 "jlpt_level":"JLPT","status":"Status","deleted_at":"Xóa lúc"}
        widths = {"id":45,"type":55,"character":90,"meaning_vi":200,
                  "jlpt_level":60,"status":90,"deleted_at":140}
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor="center")
        self.tree.column("meaning_vi", anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Status bar
        self._statusbar = ctk.CTkLabel(self, text="", height=24, anchor="w",
                                        fg_color=("gray88","gray20"),
                                        font=ctk.CTkFont(size=11), corner_radius=0)
        self._statusbar.grid(row=2, column=0, sticky="ew")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        try:
            cards = self._card_service.get_deleted()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e), parent=self)
            return
        for i, c in enumerate(cards):
            self.tree.insert("", "end", iid=str(c["id"]),
                             tags=["even" if i%2==0 else "odd"],
                             values=(
                                 c["id"],
                                 TYPE_LABELS.get(c["type"], c["type"]),
                                 c["character"],
                                 c.get("meaning_vi",""),
                                 c.get("jlpt_level",""),
                                 c.get("status",""),
                                 (c.get("deleted_at","") or "")[:16],
                             ))
        self._statusbar.configure(text=f"   {len(cards)} thẻ trong thùng rác")

    def _selected_ids(self):
        return [int(iid) for iid in self.tree.selection()]

    def _restore_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        try:
            for cid in ids:
                self._card_service.restore(cid)
            logger.info(f"Restored {len(ids)} cards: {ids}")
        except DBError as e:
            messagebox.showerror("Lỗi", str(e), parent=self)
            return
        self.refresh()
        if self.on_restore:
            self.on_restore()
        messagebox.showinfo("Khôi phục", f"Đã khôi phục {len(ids)} thẻ.", parent=self)

    def _hard_delete_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        if not messagebox.askyesno("Xóa vĩnh viễn",
                f"Xóa vĩnh viễn {len(ids)} thẻ?\nKhông thể khôi phục!", parent=self):
            return
        try:
            for cid in ids:
                self._card_service.hard_delete(cid)
            logger.info(f"Hard deleted {len(ids)} cards: {ids}")
        except DBError as e:
            messagebox.showerror("Lỗi", str(e), parent=self)
            return
        self.refresh()

    def _empty_trash(self):
        try:
            deleted = self._card_service.get_deleted()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e), parent=self)
            return
        if not deleted:
            messagebox.showinfo("Thùng rác", "Thùng rác đã sạch.", parent=self)
            return
        if not messagebox.askyesno("Dọn sạch",
                f"Xóa vĩnh viễn TẤT CẢ {len(deleted)} thẻ trong thùng rác?\nKhông thể khôi phục!",
                parent=self):
            return
        try:
            for c in deleted:
                self._card_service.hard_delete(c["id"])
            logger.info(f"Emptied trash: {len(deleted)} cards")
        except DBError as e:
            messagebox.showerror("Lỗi", str(e), parent=self)
            return
        self.refresh()
        messagebox.showinfo("Xong", "Đã dọn sạch thùng rác.", parent=self)
