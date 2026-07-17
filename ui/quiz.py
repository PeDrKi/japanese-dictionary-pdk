"""
quiz.py — Multiple choice quiz mode.
Shows a card's character → user picks correct meaning from 4 options.
Wrong answers are randomly drawn from cards of the same type.
"""
import customtkinter as ctk
import random
import logging
import tkinter as tk
from ui.tooltip import Tooltip
from constants import (
    STATUS_COLORS, COLOR_GREEN, COLOR_RED, COLOR_BLUE,
    TYPE_LABELS_FULL, CARD_TYPES, CARD_STATUSES, JLPT_LEVELS,
)

logger = logging.getLogger(__name__)


class QuizView(ctk.CTkToplevel):
    """4-option multiple choice quiz window."""

    _ANSWER_DISPLAY_MS = 1000   # how long to show correct/wrong before next card

    # Maps launcher's "Hỏi về" choice → (card field, display label)
    _ASK_MODES = {
        "meaning_vi":      ("meaning_vi",      "Nghĩa tiếng Việt"),
        "meaning_en":      ("meaning_en",      "Nghĩa tiếng Anh"),
        "romaji":          ("romaji",          "Romaji"),
        "reading_hanviet": ("reading_hanviet", "Âm Hán Việt"),
        "on":              ("on",              "Âm On-yomi"),
        "kun":             ("kun",             "Âm Kun-yomi"),
    }

    def __init__(self, master, cards: list, all_cards: list, study_service, ask_mode: str = "meaning_vi"):
        super().__init__(master)
        self.title("📝  Quiz trắc nghiệm")
        self.geometry("580x520")
        self.resizable(False, False)
        self.lift(); self.focus_force()

        self._study_service = study_service
        self._cards     = cards[:]
        self._all_cards = all_cards   # pool for wrong answer generation
        self._ask_field, self._ask_label = self._ASK_MODES.get(
            ask_mode, self._ASK_MODES["meaning_vi"])
        self._queue     = []
        self._current   = None
        self._correct   = 0
        self._wrong     = 0
        self._answered  = False

        self._build()
        self._start()

    # ── Build skeleton ────────────────────────────────────────────────────────

    def _build(self):
        # Progress bar
        prog = ctk.CTkFrame(self, fg_color=("gray90", "gray18"),
                            corner_radius=0, height=40)
        prog.pack(fill="x")
        prog.pack_propagate(False)
        prog.grid_columnconfigure(0, weight=1)

        self._prog_lbl = ctk.CTkLabel(prog, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color=("gray50", "gray55"))
        self._prog_lbl.grid(row=0, column=0, padx=14, pady=10, sticky="w")
        ctk.CTkButton(prog, text="✕ Kết thúc", width=90, height=28,
                      corner_radius=6,
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self._finish
                      ).grid(row=0, column=1, padx=14, pady=6)

        # Thin progress fill
        self._bar_bg = ctk.CTkFrame(self, fg_color=("gray80", "gray30"),
                                     height=4, corner_radius=0)
        self._bar_bg.pack(fill="x")
        self._bar_fill = ctk.CTkFrame(self._bar_bg, fg_color=COLOR_BLUE,
                                       height=4, corner_radius=0)
        self._bar_fill.place(relx=0, rely=0, relwidth=0, relheight=1)

        # Question card
        q_frame = ctk.CTkFrame(self, fg_color=("gray85", "gray20"),
                                corner_radius=14)
        q_frame.pack(fill="x", padx=24, pady=(20, 12))

        self._type_lbl = ctk.CTkLabel(q_frame, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color=("gray55", "gray55"))
        self._type_lbl.pack(pady=(14, 4))

        self._char_lbl = ctk.CTkLabel(
            q_frame, text="",
            font=ctk.CTkFont(family="Noto Sans JP", size=64, weight="bold"),
            text_color=("gray10", "gray95"))
        self._char_lbl.pack(pady=(0, 4))

        self._reading_lbl = ctk.CTkLabel(q_frame, text="",
                                          font=ctk.CTkFont(family="Noto Sans JP", size=16),
                                          text_color=("gray50", "gray55"))
        self._reading_lbl.pack(pady=(0, 14))

        # Answer buttons (2×2 grid)
        self._btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._btn_frame.pack(fill="x", padx=24, pady=8)
        self._btn_frame.grid_columnconfigure(0, weight=1)
        self._btn_frame.grid_columnconfigure(1, weight=1)

        self._ans_btns = []
        for i in range(4):
            r, c = divmod(i, 2)
            btn = ctk.CTkButton(
                self._btn_frame, text="", height=52, corner_radius=10,
                font=ctk.CTkFont(size=13),
                fg_color=("gray80", "gray28"),
                hover_color=("gray70", "gray35"),
                text_color=("gray10", "gray95"),
                command=lambda idx=i: self._answer(idx)
            )
            btn.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
            self._ans_btns.append(btn)

        # Feedback label
        self._feedback_lbl = ctk.CTkLabel(self, text="",
                                           font=ctk.CTkFont(size=14, weight="bold"))
        self._feedback_lbl.pack(pady=6)

        # Keyboard: 1-4 for answers
        for i in range(4):
            self.bind(str(i + 1), lambda _, idx=i: self._answer(idx))
        self.bind("<Escape>", lambda _: self._finish())

    # ── Session logic ─────────────────────────────────────────────────────────

    def _start(self):
        self._queue   = self._cards[:]
        random.shuffle(self._queue)
        self._correct = self._wrong = 0
        self._next()

    def _next(self):
        if not self._queue:
            self._finish()
            return
        self._answered = False
        self._current  = self._queue.pop(0)
        self._render_question()
        self._update_progress()

    def _field_value(self, card: dict, field: str = None):
        """Đọc giá trị đáp án đúng theo ask_field hiện tại.

        'on'/'kun' đọc trực tiếp cột reading_on/reading_kun (mỗi cột có
        thể chứa nhiều âm đọc cách nhau bằng '、', dùng nguyên chuỗi đó
        làm đáp án để giữ đúng các biến thể âm đọc của thẻ).
        """
        field = field or self._ask_field
        if field in ("on", "kun"):
            return card.get(f"reading_{field}") or None
        return card.get(field)

    def _render_question(self):
        c = self._current
        t = c.get("type", "")
        TYPE_LABEL = TYPE_LABELS_FULL
        jlpt  = f"  {c['jlpt_level']}" if c.get("jlpt_level") else ""
        self._type_lbl.configure(text=f"{TYPE_LABEL.get(t, t)}{jlpt}")
        self._char_lbl.configure(text=c["character"])

        # Show reading hint — skip when quizzing on romaji/on-yomi/kun-yomi
        # itself (would leak the answer)
        reading = ""
        if self._ask_field not in ("romaji", "on", "kun"):
            if t == "kanji":
                parts = [x for x in (c.get("reading_on"), c.get("reading_kun")) if x]
                reading = " / ".join(parts[:1])   # only show on-yomi as hint
            elif c.get("reading_kana"):
                reading = c["reading_kana"]
        self._reading_lbl.configure(text=reading)

        # Build 4 options: 1 correct + 3 wrong (based on selected ask mode)
        # Lưu ý: đáp án nhiễu PHẢI cùng loại dữ liệu với đáp án đúng — không
        # được rơi về nghĩa VN/EN, nếu không quiz sẽ lẫn lộn (vd hỏi Hán Việt
        # mà 1 đáp án nhiễu lại là nghĩa tiếng Việt) và lộ luôn đáp án đúng.
        correct_answer = self._field_value(c) or c.get("meaning_vi") or c.get("meaning_en") or "?"
        wrong_pool = [
            self._field_value(x)
            for x in self._all_cards
            if x["id"] != c["id"] and self._field_value(x)
        ]
        wrong_pool = list({m for m in wrong_pool if m != correct_answer})
        random.shuffle(wrong_pool)
        wrongs = wrong_pool[:3]

        # Pad if not enough wrong answers
        while len(wrongs) < 3:
            wrongs.append("—")

        options = [correct_answer] + wrongs
        random.shuffle(options)
        self._correct_idx = options.index(correct_answer)

        for i, (btn, opt) in enumerate(zip(self._ans_btns, options)):
            # Truncate long meanings
            label = f"{i+1}.  {opt[:50]}{'…' if len(opt) > 50 else ''}"
            btn.configure(
                text=label,
                fg_color=("gray80", "gray28"),
                hover_color=("gray70", "gray35"),
                text_color=("gray10", "gray95"),
                state="normal",
            )
        self._feedback_lbl.configure(text="")

    def _answer(self, idx: int):
        if self._answered:
            return
        self._answered = True
        correct = idx == self._correct_idx

        # Color feedback
        for i, btn in enumerate(self._ans_btns):
            btn.configure(state="disabled")
            if i == self._correct_idx:
                btn.configure(fg_color=COLOR_GREEN, text_color="white")
            elif i == idx and not correct:
                btn.configure(fg_color=COLOR_RED, text_color="white")

        if correct:
            self._correct += 1
            self._feedback_lbl.configure(text="✅  Chính xác!", text_color=COLOR_GREEN)
        else:
            self._wrong += 1
            correct_text = self._ans_btns[self._correct_idx].cget("text")
            self._feedback_lbl.configure(
                text=f"❌  Sai!  Đáp án: {correct_text[4:]}",
                text_color=COLOR_RED)
            # Re-insert wrong card near front of queue
            insert_at = min(3, len(self._queue))
            self._queue.insert(insert_at, self._current)

        # Log to study_sessions
        try:
            self._study_service.log_study(self._current["id"],
                      "correct" if correct else "incorrect")
        except Exception as e:
            logger.warning(f"Failed to log study result for card {self._current['id']}: {e}")

        # Auto-advance
        self.after(self._ANSWER_DISPLAY_MS, lambda: (self._next() if self.winfo_exists() else None))

    def _update_progress(self):
        done  = self._correct + self._wrong
        total = len(self._cards)
        pct   = done / total if total else 0
        acc   = round(self._correct / done * 100) if done else 0
        self._prog_lbl.configure(
            text=f"Câu {min(done+1, total)}/{total}   "
                 f"✓ {self._correct}   ✗ {self._wrong}"
                 + (f"   Độ chính xác: {acc}%" if done else ""))
        self._bar_fill.place(relwidth=pct)

    def _finish(self):
        done = self._correct + self._wrong
        acc  = round(self._correct / done * 100) if done else 0
        for w in self.winfo_children():
            w.destroy()

        ctk.CTkLabel(self, text="📝  Kết quả Quiz",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(40, 20))

        stats = ctk.CTkFrame(self, fg_color=("gray85", "gray20"), corner_radius=12)
        stats.pack(padx=40, fill="x")
        for label, val, color in [
            ("✅  Trả lời đúng",   str(self._correct), COLOR_GREEN),
            ("❌  Trả lời sai",    str(self._wrong),   COLOR_RED),
            ("📊  Độ chính xác",   f"{acc}%",          COLOR_BLUE),
            ("📚  Tổng câu hỏi",   str(len(self._cards)), "gray"),
        ]:
            row = ctk.CTkFrame(stats, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=6)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=13),
                         anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=val,
                         font=ctk.CTkFont(size=18, weight="bold"),
                         text_color=color).pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=40, pady=28)
        ctk.CTkButton(btn_row, text="✕  Đóng",
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy, height=42
                      ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(btn_row, text="🔄  Làm lại",
                      command=self._restart, height=42
                      ).pack(side="right", fill="x", expand=True, padx=(8, 0))

    def _restart(self):
        for w in self.winfo_children():
            w.destroy()
        self._build()
        self._start()


# ── Launcher dialog ───────────────────────────────────────────────────────────

class QuizLauncher(ctk.CTkToplevel):
    """Let user configure quiz parameters before starting."""

    # Maps the "Hỏi về" dropdown label -> card field used as the answer
    _MODE_TO_FIELD = {
        "Nghĩa VN":     "meaning_vi",
        "Nghĩa EN":     "meaning_en",
        "Romaji":       "romaji",
        "Hán Việt":     "reading_hanviet",
        "Âm On-yomi":   "on",
        "Âm Kun-yomi":  "kun",
    }

    def __init__(self, master, card_service, deck_service, study_service, default_due_only=False):
        super().__init__(master)
        self._card_service  = card_service
        self._deck_service  = deck_service
        self._study_service = study_service
        self._default_due_only = default_due_only
        self.title("📝  Cài đặt Quiz")
        self.geometry("420x540")
        self.minsize(420, 400)
        self.resizable(True, True)
        self.grab_set(); self.lift(); self.focus_force()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="📝  Quiz Trắc Nghiệm",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(24, 4))
        self._subtitle_lbl = ctk.CTkLabel(
            self, text="Chọn đúng nghĩa tiếng Việt trong 4 đáp án",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"))
        self._subtitle_lbl.pack(pady=(0, 16))

        # Nút Hủy / Bắt đầu Quiz pack "side=bottom" TRƯỚC vùng cuộn, để luôn
        # được dành chỗ và hiển thị ở đáy cửa sổ dù nội dung bộ lọc dài bao nhiêu.
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=24, pady=(8, 24))
        ctk.CTkButton(btn_row, text="✕  Hủy",
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy, height=42
                      ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(btn_row, text="▶  Bắt đầu Quiz",
                      command=self._launch, height=42
                      ).pack(side="right", fill="x", expand=True, padx=(8, 0))

        self._count_lbl = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color=("gray50", "gray55"))
        self._count_lbl.pack(side="bottom", pady=12)

        # Vùng bộ lọc có thể cuộn — không còn nguy cơ đẩy nút Bắt đầu ra ngoài màn hình
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=0)

        f = ctk.CTkFrame(body, fg_color=("gray88", "gray20"), corner_radius=12)
        f.pack(fill="x", padx=16, pady=4)

        def row(parent, label, widget_fn):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=6)
            r.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, width=80,
                         font=ctk.CTkFont(size=12), anchor="w"
                         ).grid(row=0, column=0, sticky="w")
            w = widget_fn(r)
            w.grid(row=0, column=1, sticky="ew", padx=(8, 0))
            return w

        self._type_var   = ctk.StringVar(value="Tất cả")
        self._jlpt_var   = ctk.StringVar(value="Tất cả")
        self._status_var = ctk.StringVar(value="Tất cả")
        self._deck_var   = ctk.StringVar(value="Tất cả")
        self._limit_var  = ctk.StringVar(value="20")
        self._mode_var   = ctk.StringVar(value="Nghĩa VN")

        decks = self._deck_service.list_decks()
        self._deck_name_to_id = {d["name"]: d["id"] for d in decks}

        row(f, "Loại",    lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"] + CARD_TYPES, variable=self._type_var))
        row(f, "JLPT",    lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"] + JLPT_LEVELS, variable=self._jlpt_var))
        row(f, "Status",  lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"] + CARD_STATUSES, variable=self._status_var))
        row(f, "Deck",    lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"] + list(self._deck_name_to_id), variable=self._deck_var))
        row(f, "Số câu",  lambda p: ctk.CTkOptionMenu(
            p, values=["10", "20", "30", "50", "Tất cả"], variable=self._limit_var))
        row(f, "Hỏi về", lambda p: ctk.CTkOptionMenu(
            p, values=["Nghĩa VN", "Nghĩa EN", "Romaji", "Hán Việt",
                       "Âm On-yomi", "Âm Kun-yomi"],
            variable=self._mode_var))

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

        for v in [self._type_var, self._jlpt_var, self._status_var,
                  self._deck_var, self._limit_var, self._mode_var, self._due_var]:
            v.trace_add("write", lambda *_: self._update_count())
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
        # Only keep cards that actually have data for the selected quiz mode
        field = self._MODE_TO_FIELD.get(self._mode_var.get(), "meaning_vi")
        if field in ("on", "kun"):
            cards = [c for c in cards if c.get("type") == "kanji"
                     and c.get(f"reading_{field}")]
        else:
            cards = [c for c in cards if c.get(field)]
        limit = self._limit_var.get()
        if limit != "Tất cả":
            cards = cards[:int(limit)]
        return cards

    def _update_count(self):
        try:
            n = len(self._get_cards())
            color = "#4ECB85" if n >= 4 else "#E85D5D"
            self._count_lbl.configure(
                text=f"Sẽ quiz {n} thẻ" + (" (cần ít nhất 4)" if n < 4 else ""),
                text_color=color)
            mode_label = self._mode_var.get()
            self._subtitle_lbl.configure(
                text=f"Chọn đúng {mode_label.lower()} trong 4 đáp án")
        except Exception:
            pass

    def _launch(self):
        cards = self._get_cards()
        if len(cards) < 4:
            return
        # Load all cards as wrong-answer pool
        all_cards = self._card_service.list_cards()
        ask_mode = self._MODE_TO_FIELD.get(self._mode_var.get(), "meaning_vi")
        self.destroy()
        QuizView(self.master, cards, all_cards, self._study_service, ask_mode=ask_mode)
