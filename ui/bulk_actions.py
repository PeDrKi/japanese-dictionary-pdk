"""
bulk_actions.py — Bulk operation bar shown when multiple rows are selected.
All DB operations go through CardService/DeckService (no raw SQL, no
direct database.models calls here).
"""
import customtkinter as ctk
from tkinter import messagebox
from database.models import DBError
from constants import (
    STATUS_NEW, STATUS_LEARNING, STATUS_KNOWN,
    RESULT_CORRECT, RESULT_INCORRECT,
)
import logging

logger = logging.getLogger(__name__)


class BulkBar(ctk.CTkFrame):
    """
    Blue bar shown at bottom when >1 rows are selected.
    Communicates back to TableView via on_done callback.
    """

    def __init__(self, master, card_service, deck_service, on_done, **kwargs):
        super().__init__(master, fg_color=("#1e3a5f", "#1e3a5f"),
                         corner_radius=0, height=46, **kwargs)
        self.grid_propagate(False)
        self._card_service = card_service
        self._deck_service  = deck_service
        self._on_done    = on_done
        self._get_ids_fn = None
        self._build()

    def set_ids_fn(self, fn):
        self._get_ids_fn = fn

    def _get_ids(self) -> list:
        return self._get_ids_fn() if self._get_ids_fn else []

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(99, weight=1)
        bkb = dict(height=30, corner_radius=6,
                   fg_color=("gray60", "gray40"), text_color="white")

        self._lbl = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white")
        self._lbl.grid(row=0, column=0, padx=14, pady=12)

        ctk.CTkButton(self, text="✅ Known",
                      command=lambda: self._set_status(STATUS_KNOWN), **bkb
                      ).grid(row=0, column=1, padx=4, pady=8)
        ctk.CTkButton(self, text="📖 Learning",
                      command=lambda: self._set_status(STATUS_LEARNING), **bkb
                      ).grid(row=0, column=2, padx=4, pady=8)
        ctk.CTkButton(self, text="🆕 New",
                      command=lambda: self._set_status(STATUS_NEW), **bkb
                      ).grid(row=0, column=3, padx=4, pady=8)
        ctk.CTkButton(self, text="⭐ Yêu thích",
                      command=self._toggle_fav, **bkb
                      ).grid(row=0, column=4, padx=4, pady=8)
        ctk.CTkButton(self, text="📁 Thêm vào Deck",
                      command=self._open_add_to_deck, **bkb
                      ).grid(row=0, column=5, padx=4, pady=8)
        ctk.CTkButton(self, text="🗑️ Xóa",
                      command=self._delete,
                      fg_color="#c0392b", text_color="white",
                      hover_color="#922b21", height=30, corner_radius=6
                      ).grid(row=0, column=6, padx=(4, 14), pady=8)

    def update_count(self, n: int):
        self._lbl.configure(text=f"✓  {n} thẻ đã chọn")

    # ── Actions — all DB calls go through models ───────────────────────────────

    def _set_status(self, status: str):
        ids = self._get_ids()
        if not ids:
            return
        try:
            self._card_service.bulk_update_status(ids, status)
            logger.info(f"Bulk status={status} for {len(ids)} cards: {ids}")
            self._on_done()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e))

    def _toggle_fav(self):
        ids = self._get_ids()
        if not ids:
            return
        try:
            self._card_service.bulk_toggle_favorite(ids)
            logger.info(f"Bulk toggle favorite for {len(ids)} cards: {ids}")
            self._on_done()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e))

    def _open_add_to_deck(self):
        ids = self._get_ids()
        if not ids:
            return
        try:
            decks = self._deck_service.list_decks()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e))
            return
        if not decks:
            messagebox.showinfo(
                "Chưa có Deck",
                "Bạn chưa tạo Deck nào.\nHãy tạo 1 Deck ở sidebar (nút ＋ cạnh '📁 BỘ THẺ') trước.")
            return
        AddToDeckDialog(self, decks, ids, on_done=self._on_add_to_deck_done)

    def _on_add_to_deck_done(self, deck_id, ids):
        try:
            self._deck_service.bulk_add_cards(deck_id, ids)
            logger.info(f"Bulk add {len(ids)} cards to deck {deck_id}: {ids}")
            self._on_done()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e))

    def _delete(self):
        ids = self._get_ids()
        if not ids:
            return
        if not messagebox.askyesno(
                "Xóa hàng loạt",
                f"Chuyển {len(ids)} thẻ vào thùng rác?\nBạn có thể khôi phục sau."):
            return
        try:
            self._card_service.bulk_soft_delete(ids)
            logger.info(f"Bulk soft delete {len(ids)} cards: {ids}")
            self._on_done()
        except DBError as e:
            messagebox.showerror("Lỗi", str(e))


class AddToDeckDialog(ctk.CTkToplevel):
    """Small popup: pick which deck to add the currently-selected cards to."""

    def __init__(self, master, decks: list, card_ids: list, on_done):
        super().__init__(master)
        self._decks    = decks
        self._card_ids = card_ids
        self._on_done  = on_done

        self.title("📁  Thêm vào Deck")
        self.geometry("340x360")
        self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text=f"Thêm {len(self._card_ids)} thẻ vào deck nào?",
                     font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(pady=(20, 12), padx=20)

        scroll = ctk.CTkScrollableFrame(self, fg_color=("gray90", "gray17"))
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        self._deck_var = ctk.IntVar(value=self._decks[0]["id"])
        for d in self._decks:
            ctk.CTkRadioButton(
                scroll, text=f"{d.get('icon') or '📁'}  {d['name']} ({d.get('card_count', 0)} thẻ)",
                variable=self._deck_var, value=d["id"]
            ).pack(anchor="w", padx=8, pady=6)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btn_row, text="✕ Hủy",
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy, height=38
                      ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(btn_row, text="✓ Thêm",
                      command=self._confirm, height=38
                      ).pack(side="right", fill="x", expand=True, padx=(8, 0))

    def _confirm(self):
        deck_id = self._deck_var.get()
        self.destroy()
        self._on_done(deck_id, self._card_ids)
