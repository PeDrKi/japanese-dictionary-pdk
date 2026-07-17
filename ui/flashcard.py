import customtkinter as ctk
import random
from ui.tooltip import Tooltip
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


class FlashcardView(ctk.CTkToplevel):
    """
    Standalone flashcard window.
    Launched from the main app; user picks a filter first.
    """

    def __init__(self, master, cards: list, study_service):
        super().__init__(master)
        self.title("🃏  Ôn luyện Flashcard")
        self.geometry("560x480")
        self.resizable(False, False)
        self.lift(); self.focus_force()

        self._study_service = study_service
        self._cards     = cards[:]
        self._queue     = []
        self._current   = None
        self._revealed  = False
        self._correct   = 0
        self._incorrect = 0
        self._total     = len(cards)

        self._build()
        self._start_session()

    # ── Build skeleton ────────────────────────────────────────────────────────

    def _build(self):
        # Progress bar row
        prog_row = ctk.CTkFrame(self, fg_color=("gray90","gray18"),
                                corner_radius=0, height=40)
        prog_row.pack(fill="x")
        prog_row.pack_propagate(False)
        prog_row.grid_columnconfigure(0, weight=1)

        self._prog_lbl = ctk.CTkLabel(prog_row, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color=("gray50","gray55"))
        self._prog_lbl.grid(row=0, column=0, padx=14, pady=10, sticky="w")

        ctk.CTkButton(prog_row, text="✕ Kết thúc", width=90, height=28,
                      corner_radius=6,
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self._end_session
                      ).grid(row=0, column=1, padx=14, pady=6)

        # Progress bar
        self._prog_bg = ctk.CTkFrame(self, fg_color=("gray80","gray30"),
                                      height=4, corner_radius=0)
        self._prog_bg.pack(fill="x")
        self._prog_fill = ctk.CTkFrame(self._prog_bg, fg_color="#4A90D9",
                                        height=4, corner_radius=0)
        self._prog_fill.place(relx=0, rely=0, relwidth=0, relheight=1)

        # Card face
        self._card_frame = ctk.CTkFrame(self, fg_color=("gray85","gray20"),
                                         corner_radius=16)
        self._card_frame.pack(fill="both", expand=True, padx=24, pady=20)

        # Front: big character
        self._char_lbl = ctk.CTkLabel(
            self._card_frame, text="",
            font=ctk.CTkFont(family="Noto Sans JP", size=72, weight="bold"),
            text_color=("gray10","gray95"))
        self._char_lbl.pack(expand=True)

        # Front: type badge
        self._type_lbl = ctk.CTkLabel(
            self._card_frame, text="",
            font=ctk.CTkFont(size=11), text_color=("gray55","gray55"))
        self._type_lbl.pack(pady=(0,8))

        # Back content (hidden initially)
        self._back_frame = ctk.CTkFrame(self._card_frame, fg_color="transparent")

        self._reading_lbl = ctk.CTkLabel(
            self._back_frame, text="",
            font=ctk.CTkFont(family="Noto Sans JP", size=20),
            text_color=("#3ECFCF","#3ECFCF"))
        self._reading_lbl.pack(pady=(0,4))

        self._meaning_lbl = ctk.CTkLabel(
            self._back_frame, text="",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=("#4ECB85","#4ECB85"))
        self._meaning_lbl.pack(pady=4)

        self._example_lbl = ctk.CTkLabel(
            self._back_frame, text="",
            font=ctk.CTkFont(family="Noto Sans JP", size=13),
            text_color=("gray50","gray55"),
            wraplength=460, justify="center")
        self._example_lbl.pack(pady=(8,0))

        # Hint: press space
        self._hint_lbl = ctk.CTkLabel(
            self._card_frame,
            text="[ Space / Click để lật thẻ ]",
            font=ctk.CTkFont(size=11),
            text_color=("gray65","gray50"))
        self._hint_lbl.pack(pady=(0,16))

        # Action buttons (hidden until revealed)
        self._btn_row = ctk.CTkFrame(self, fg_color="transparent", height=64)
        self._btn_row.pack(fill="x", padx=24, pady=(0,20))
        self._btn_row.pack_propagate(False)

        self._wrong_btn = ctk.CTkButton(
            self._btn_row, text="✗  Không nhớ",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#c0392b", hover_color="#922b21",
            height=48, corner_radius=10,
            command=lambda: self._answer(False))
        self._wrong_btn.pack(side="left", fill="x", expand=True, padx=(0,8))

        self._right_btn = ctk.CTkButton(
            self._btn_row, text="✓  Đã nhớ",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#27ae60", hover_color="#1e8449",
            height=48, corner_radius=10,
            command=lambda: self._answer(True))
        self._right_btn.pack(side="right", fill="x", expand=True, padx=(8,0))

        self._btn_row.pack_forget()   # hidden until card is revealed

        # Reveal button
        self._reveal_btn = ctk.CTkButton(
            self, text="👁  Lật thẻ  (Space)",
            font=ctk.CTkFont(size=14),
            height=48, corner_radius=10,
            command=self._reveal)
        self._reveal_btn.pack(fill="x", padx=24, pady=(0,20))

        # Keyboard bindings
        self.bind("<space>",   lambda _: self._on_space())
        self.bind("<Return>",  lambda _: self._on_space())
        self.bind("<Left>",    lambda _: self._answer(False) if self._revealed else None)
        self.bind("<Right>",   lambda _: self._answer(True)  if self._revealed else None)
        self._card_frame.bind("<Button-1>", lambda _: self._on_space())

    # ── Session logic ─────────────────────────────────────────────────────────

    def _start_session(self):
        self._queue = self._cards[:]
        random.shuffle(self._queue)
        self._correct = self._incorrect = 0
        self._next_card()

    def _next_card(self):
        if not self._queue:
            self._end_session()
            return
        self._current  = self._queue.pop(0)
        self._revealed = False
        self._show_front()
        self._update_progress()

    def _show_front(self):
        c = self._current
        self._char_lbl.configure(text=c["character"])

        TYPE_LABEL = {"kanji":"漢字","hiragana":"ひらがな","katakana":"カタカナ","vocab":"語彙"}
        jlpt = f"  {c['jlpt_level']}" if c.get("jlpt_level") else ""
        self._type_lbl.configure(text=f"{TYPE_LABEL.get(c['type'],c['type'])}{jlpt}")

        self._back_frame.pack_forget()
        self._hint_lbl.pack(pady=(0,16))
        self._reveal_btn.pack(fill="x", padx=24, pady=(0,20))
        self._btn_row.pack_forget()

    def _reveal(self):
        if self._revealed:
            return
        self._revealed = True
        c = self._current

        # Build reading string
        if c["type"] == "kanji":
            parts = [x for x in [c.get("reading_on"), c.get("reading_kun")] if x]
            reading = "  /  ".join(parts)
        elif c.get("reading_kana"):
            reading = c["reading_kana"]
        else:
            reading = c.get("romaji","")

        self._reading_lbl.configure(text=reading)
        self._meaning_lbl.configure(text=c.get("meaning_vi",""))

        ex = ""
        if c.get("example_jp"):
            ex = c["example_jp"]
            if c.get("example_vi"):
                ex += f"\n{c['example_vi']}"
        self._example_lbl.configure(text=ex)

        self._hint_lbl.pack_forget()
        self._back_frame.pack(expand=True, pady=8)
        self._reveal_btn.pack_forget()
        self._btn_row.pack(fill="x", padx=24, pady=(0,20))

    def _answer(self, correct: bool):
        if not self._revealed:
            return
        if correct:
            self._correct += 1
        else:
            self._incorrect += 1
            # Put back in queue so user sees it again
            insert_at = min(3, len(self._queue))
            self._queue.insert(insert_at, self._current)

        self._study_service.log_study(self._current["id"], "correct" if correct else "incorrect")
        self._next_card()

    def _on_space(self):
        if self._revealed:
            pass   # use arrow keys after reveal
        else:
            self._reveal()

    def _update_progress(self):
        done   = self._total - len(self._queue) - (1 if self._current else 0)
        done   = max(0, done)
        total  = self._total
        pct    = done / total if total else 0
        acc    = round(self._correct / (self._correct+self._incorrect)*100) \
                 if (self._correct+self._incorrect) else 0

        self._prog_lbl.configure(
            text=f"Thẻ {done+1}/{total}   ✓ {self._correct}   ✗ {self._incorrect}"
                 + (f"   Độ chính xác: {acc}%" if (self._correct+self._incorrect) else ""))
        self._prog_fill.place(relwidth=pct)

    def _end_session(self):
        total = self._correct + self._incorrect
        acc   = round(self._correct / total * 100) if total else 0
        self._show_result(self._correct, self._incorrect, acc)

    def _show_result(self, correct, incorrect, acc):
        for w in self.winfo_children():
            w.destroy()

        ctk.CTkLabel(self, text="🎉  Kết quả phiên ôn",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(40,24))

        stats = ctk.CTkFrame(self, fg_color=("gray85","gray20"), corner_radius=12)
        stats.pack(padx=40, fill="x")

        rows = [
            ("✅  Đã nhớ",    str(correct),            "#4ECB85"),
            ("❌  Không nhớ", str(incorrect),           "#E85D5D"),
            ("📊  Độ chính xác", f"{acc}%",             "#4A90D9"),
            ("📚  Tổng thẻ",  str(self._total),         "gray"),
        ]
        for label, val, color in rows:
            row = ctk.CTkFrame(stats, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=6)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(size=13), anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=val,
                         font=ctk.CTkFont(size=18, weight="bold"),
                         text_color=color).pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=40, pady=32)
        ctk.CTkButton(btn_row, text="✕  Đóng",
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.destroy, height=42).pack(side="left", fill="x", expand=True, padx=(0,8))
        ctk.CTkButton(btn_row, text="🔄  Ôn lại",
                      command=self._restart, height=42).pack(side="right", fill="x", expand=True, padx=(8,0))

    def _restart(self):
        for w in self.winfo_children():
            w.destroy()
        self._build()
        self._start_session()


# ── Launch dialog ─────────────────────────────────────────────────────────────

class FlashcardLauncher(ctk.CTkToplevel):
    """Dialog to pick which cards to study before launching flashcard session."""

    def __init__(self, master, card_service, deck_service, study_service, default_due_only=False):
        super().__init__(master)
        self._card_service  = card_service
        self._deck_service  = deck_service
        self._study_service = study_service
        self._default_due_only = default_due_only
        self.title("🃏  Bắt đầu ôn luyện")
        self.geometry("400x480")
        self.minsize(400, 380)
        self.resizable(True, True)
        self.grab_set(); self.lift(); self.focus_force()
        self._build()
        self.bind(KB_ESCAPE, lambda _: self.destroy())

    def _build(self):
        ctk.CTkLabel(self, text="🃏  Chọn bộ thẻ để ôn",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(24,4))
        ctk.CTkLabel(self, text="Chỉ lấy thẻ khớp với bộ lọc bên dưới",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")).pack(pady=(0,16))

        # Nút Hủy / Bắt đầu pack "side=bottom" TRƯỚC vùng cuộn, để luôn
        # được dành chỗ và hiển thị ở đáy cửa sổ dù nội dung bộ lọc dài bao nhiêu.
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=24, pady=(8,24))
        ctk.CTkButton(btn_row, text="✕  Hủy",
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy, height=42
                      ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(btn_row, text="▶  Bắt đầu",
                      command=self._launch, height=42
                      ).pack(side="right", fill="x", expand=True, padx=(8, 0))

        self._count_lbl = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color=("gray50", "gray55"))
        self._count_lbl.pack(side="bottom", pady=12)

        # Vùng bộ lọc có thể cuộn — không còn nguy cơ đẩy nút Bắt đầu ra ngoài màn hình
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=0)

        f = ctk.CTkFrame(body, fg_color=("gray88","gray20"), corner_radius=12)
        f.pack(fill="x", padx=16, pady=4)

        def row(parent, label, widget_fn):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=6)
            r.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, width=80,
                         font=ctk.CTkFont(size=12), anchor="w").grid(row=0,column=0,sticky="w")
            w = widget_fn(r)
            w.grid(row=0, column=1, sticky="ew", padx=(8,0))
            return w

        self._type_var   = ctk.StringVar(value="Tất cả")
        self._jlpt_var   = ctk.StringVar(value="Tất cả")
        self._status_var = ctk.StringVar(value="Tất cả")
        self._deck_var   = ctk.StringVar(value="Tất cả")
        self._limit_var  = ctk.StringVar(value="20")

        decks = self._deck_service.list_decks()
        self._deck_name_to_id = {d["name"]: d["id"] for d in decks}

        row(f, "Loại",     lambda p: ctk.CTkOptionMenu(p, values=["Tất cả","kanji","hiragana","katakana","vocab"],
                                                        variable=self._type_var))
        row(f, "JLPT",     lambda p: ctk.CTkOptionMenu(p, values=["Tất cả","N5","N4","N3","N2","N1"],
                                                        variable=self._jlpt_var))
        row(f, "Status",   lambda p: ctk.CTkOptionMenu(p, values=["Tất cả","new","learning","known"],
                                                        variable=self._status_var))
        row(f, "Deck",     lambda p: ctk.CTkOptionMenu(p, values=["Tất cả"] + list(self._deck_name_to_id),
                                                        variable=self._deck_var))
        row(f, "Số thẻ",   lambda p: ctk.CTkOptionMenu(p, values=["10","20","30","50","Tất cả"],
                                                        variable=self._limit_var))

        self._due_var = ctk.BooleanVar(value=self._default_due_only)
        due_row = ctk.CTkFrame(f, fg_color="transparent")
        due_row.pack(fill="x", padx=16, pady=(2, 8))
        due_count = self._card_service.due_count()
        due_cb = ctk.CTkCheckBox(due_row, text=f"🎯 Chỉ ôn thẻ đến hạn ({due_count})",
                         variable=self._due_var,
                         font=ctk.CTkFont(size=12))
        due_cb.pack(anchor="w")
        Tooltip(due_cb, "Chỉ lấy các thẻ đã đến lịch ôn lại (SRS), "
                        "bỏ qua thẻ vừa ôn gần đây và chưa cần ôn lại.")

        for var in [self._type_var, self._jlpt_var, self._status_var, self._deck_var,
                    self._limit_var, self._due_var]:
            var.trace_add("write", lambda *_: self._update_count())
        self._update_count()

    def _get_cards(self):
        kw = {}
        if self._type_var.get()   != "Tất cả": kw["type_filter"]   = self._type_var.get()
        if self._jlpt_var.get()   != "Tất cả": kw["jlpt_filter"]   = self._jlpt_var.get()
        if self._status_var.get() != "Tất cả": kw["status_filter"] = self._status_var.get()
        if self._deck_var.get()   != "Tất cả":
            kw["deck_id"] = self._deck_name_to_id.get(self._deck_var.get())
        if self._due_var.get():
            kw["due_only"] = True
        cards = self._card_service.list_cards(**kw)
        limit = self._limit_var.get()
        if limit != "Tất cả":
            cards = cards[:int(limit)]
        return cards

    def _update_count(self):
        try:
            n = len(self._get_cards())
            self._count_lbl.configure(text=f"Sẽ ôn {n} thẻ")
        except Exception:
            pass

    def _launch(self):
        cards = self._get_cards()
        if not cards:
            return
        self.destroy()
        FlashcardView(self.master, cards, self._study_service)
