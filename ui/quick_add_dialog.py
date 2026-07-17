"""
ui/quick_add_dialog.py — "⚡ Nhập nhanh" (quick add): paste multiple lines
of "character - meaning" and create several cards at once, instead of
opening CardForm N times.

Parsing itself lives in domain/quick_add_parser.py (pure, unit tested);
this file only handles the paste → preview → create workflow and talks
to CardService for validation/persistence — same pattern the rest of the
app already uses (see application/card_service.py's validate_and_build,
used the same way by ui/card_form.py).
"""
import customtkinter as ctk
from tkinter import messagebox

from domain.quick_add_parser import parse_quick_add_text
from constants import CARD_TYPES, TYPE_LABELS_FULL


class QuickAddDialog(ctk.CTkToplevel):
    def __init__(self, master, card_service, on_done=None):
        super().__init__(master)
        self._card_service = card_service
        self._on_done = on_done
        self._rows = []   # last parse_quick_add_text() result

        self.title("⚡  Nhập nhanh nhiều thẻ")
        self.geometry("560x620")
        self.minsize(480, 480)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self.focus_force()

        self._build()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        ctk.CTkLabel(
            self, anchor="w", justify="left", font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
            text=("Dán mỗi thẻ một dòng, theo dạng:  chữ - nghĩa tiếng Việt\n"
                  "Nhận cả dấu \"-\", \":\", hoặc Tab (dán từ Excel/Sheets) làm dấu ngăn cách.\n"
                  "Ví dụ:   猫 - con mèo")
        ).pack(fill="x", padx=20, pady=(16, 8))

        type_row = ctk.CTkFrame(self, fg_color="transparent")
        type_row.pack(fill="x", padx=20)
        ctk.CTkLabel(type_row, text="Loại thẻ (áp dụng cho tất cả):",
                     font=ctk.CTkFont(size=12)).pack(side="left")
        self._type_var = ctk.StringVar(value=CARD_TYPES[0])
        ctk.CTkOptionMenu(
            type_row, values=CARD_TYPES, variable=self._type_var,
            width=140,
            dynamic_resizing=False
        ).pack(side="left", padx=(8, 0))

        self._input_box = ctk.CTkTextbox(self, height=160)
        self._input_box.pack(fill="both", expand=False, padx=20, pady=(10, 8))

        ctk.CTkButton(self, text="🔍  Xem trước", command=self._preview
                      ).pack(padx=20, anchor="w")

        self._preview_label = ctk.CTkLabel(
            self, anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
        self._preview_label.pack(fill="x", padx=20, pady=(10, 4))

        self._preview_scroll = ctk.CTkScrollableFrame(self, fg_color=("gray92", "gray17"))
        self._preview_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btns, text="✕  Hủy",
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy, width=100).pack(side="left")
        self._create_btn = ctk.CTkButton(
            btns, text="Tạo thẻ", command=self._create_cards,
            height=38, state="disabled")
        self._create_btn.pack(side="right")

    # ── Preview ──────────────────────────────────────────────────────────────

    def _preview(self):
        text = self._input_box.get("1.0", "end-1c")
        self._rows = parse_quick_add_text(text)

        for w in self._preview_scroll.winfo_children():
            w.destroy()

        if not self._rows:
            self._preview_label.configure(text="Chưa có dòng nào để xem trước.")
            self._create_btn.configure(state="disabled", text="Tạo thẻ")
            return

        card_type = self._type_var.get()
        valid_rows = [r for r in self._rows if r["valid"]]

        # Flag likely duplicates up front (character+type already in the
        # library) so the user can decide to remove those lines — bulk
        # add can't reasonably pop a confirm dialog per row like CardForm
        # does for a single card.
        dupe_ids = set()
        for r in valid_rows:
            try:
                if self._card_service.check_duplicates(r["character"], card_type):
                    dupe_ids.add(id(r))
            except Exception:
                pass

        for r in self._rows:
            if not r["valid"]:
                text_line = f'✗  "{r["raw"].strip()}"  —  {r["error"]}'
                color = "#E85D5D"
            elif id(r) in dupe_ids:
                text_line = f'⚠  {r["character"]}  —  {r["meaning_vi"]}  (đã có thẻ trùng)'
                color = "#E8A33D"
            else:
                text_line = f'✓  {r["character"]}  —  {r["meaning_vi"]}'
                color = ("gray10", "gray90")
            ctk.CTkLabel(self._preview_scroll, text=text_line, anchor="w",
                         text_color=color, font=ctk.CTkFont(size=12)
                         ).pack(fill="x", padx=6, pady=1)

        n_valid, n_total = len(valid_rows), len(self._rows)
        n_dupe = len(dupe_ids)
        summary = f"{n_valid}/{n_total} dòng hợp lệ"
        if n_dupe:
            summary += f" ({n_dupe} có thể trùng lặp)"
        self._preview_label.configure(text=summary)

        if n_valid:
            self._create_btn.configure(state="normal", text=f"Tạo {n_valid} thẻ")
        else:
            self._create_btn.configure(state="disabled", text="Tạo thẻ")

    # ── Create ───────────────────────────────────────────────────────────────

    def _create_cards(self):
        card_type = self._type_var.get()
        valid_rows = [r for r in self._rows if r["valid"]]
        if not valid_rows:
            return

        created = 0
        for r in valid_rows:
            data, check = self._card_service.validate_and_build(
                card_type=card_type,
                character=r["character"],
                meaning_vi=r["meaning_vi"],
            )
            if data is None:
                continue   # shouldn't happen — parser already required both fields
            self._card_service.add(data)
            created += 1

        type_label = TYPE_LABELS_FULL.get(card_type, card_type)
        messagebox.showinfo(
            "Hoàn tất", f"Đã tạo {created} thẻ ({type_label}) mới.", parent=self)

        if self._on_done:
            self._on_done()
        self.destroy()
