"""
typing_practice.py — Typing practice mode.
Shows a card → user types the correct answer (kana/romaji/meaning).
Checks answer with flexible matching (case-insensitive, trim, romaji variants).
"""
import customtkinter as ctk
import random
import logging
from ui.tooltip import Tooltip
from domain.kana import kana_to_romaji
from constants import (
    COLOR_GREEN, COLOR_RED, COLOR_BLUE, COLOR_GOLD,
    CARD_TYPES, CARD_STATUSES, JLPT_LEVELS,
    TYPE_LABELS_FULL, KB_ESCAPE,
)

logger = logging.getLogger(__name__)


def expand_kana_items(cards, split_readings: bool = True):
    """
    Turn a list of cards into the flat list of "kana" quiz items actually
    asked. With split_readings=True, a kanji card's on-yomi/kun-yomi
    (each "、"-separated, see domain.validators.normalize_multi_reading)
    are expanded into one item per individual reading, tagged with which
    reading it is — so a kanji like 月 (on: げつ、がつ / kun: つき)
    produces 3 separate quiz items instead of 1. With split_readings=False,
    each card stays a single item (any of its readings is accepted).
    """
    if not split_readings:
        return [dict(c) for c in cards]

    items = []
    for c in cards:
        t = c.get("type", "")
        if t == "kanji":
            on_list  = [x.strip() for x in (c.get("reading_on")  or "").split("、") if x.strip()]
            kun_list = [x.strip() for x in (c.get("reading_kun") or "").split("、") if x.strip()]
            readings = [("on", v) for v in on_list] + [("kun", v) for v in kun_list]
            if not readings:
                continue
            total = len(readings)
            for idx, (rtype, val) in enumerate(readings, start=1):
                item = dict(c)
                item["_reading_type"]  = rtype
                item["_reading_value"] = val
                item["_reading_pos"]   = f"{idx}/{total}" if total > 1 else ""
                items.append(item)
        else:
            kana = c.get("reading_kana") or c.get("reading_kun") or ""
            if not kana:
                continue
            item = dict(c)
            item["_reading_type"]  = "kana"
            item["_reading_value"] = kana
            item["_reading_pos"]   = ""
            items.append(item)
    return items


def expand_reading_items(cards, kind: str):
    """
    Giống expand_kana_items nhưng CHỈ lấy 1 loại âm đọc duy nhất (on-yomi
    HOẶC kun-yomi, không trộn cả hai) — dùng cho 2 chế độ "Âm On-yomi" /
    "Âm Kun-yomi" tách riêng trong Luyện gõ. Mỗi âm đọc (cách nhau bằng
    "、", xem domain.validators.normalize_multi_reading) được tách thành
    1 câu hỏi riêng, vd 月 kun-yomi "つき" chỉ có 1 câu, còn on-yomi
    "げつ、がつ" tách thành 2 câu.
    """
    field = f"reading_{kind}"
    items = []
    for c in cards:
        if c.get("type") != "kanji":
            continue
        raw = c.get(field) or ""
        vals = [x.strip() for x in raw.split("、") if x.strip()]
        if not vals:
            continue
        total = len(vals)
        for idx, val in enumerate(vals, start=1):
            item = dict(c)
            item["_reading_type"]  = kind
            item["_reading_value"] = val
            item["_reading_pos"]   = f"{idx}/{total}" if total > 1 else ""
            items.append(item)
    return items


class TypingView(ctk.CTkToplevel):
    """
    Typing practice window.
    Ask mode options:
      "romaji"   — type the romaji reading
      "meaning"  — type the Vietnamese meaning
      "kana"     — type the kana / on-yomi / kun-yomi reading (mixed)
      "on"       — type ONLY the on-yomi reading (kanji only)
      "kun"      — type ONLY the kun-yomi reading (kanji only)
      "hanviet"  — type the Hán Việt (Sino-Vietnamese) reading
    """

    _NEXT_DELAY_MS = 1200

    def __init__(self, master, cards: list, study_service, ask_mode: str = "meaning",
                 split_readings: bool = True):
        super().__init__(master)
        self.title("⌨️  Luyện gõ")
        self.geometry("560x500")
        self.resizable(False, False)
        self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())

        self._study_service = study_service
        self._cards         = cards[:]
        self._ask_mode      = ask_mode
        # When True and ask_mode == "kana": a kanji with several on/kun
        # readings (e.g. 月 → げつ、がつ / つき) is split into one quiz
        # item per individual reading, each graded on that reading alone,
        # instead of one item per card that accepts any of its readings.
        self._split_readings = split_readings
        self._queue    = []
        self._session_items = []   # the (possibly expanded) item list for this run
        self._current  = None
        self._correct  = 0
        self._wrong    = 0
        self._answered = False

        self._build()
        self._start()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        # Progress bar
        prog = ctk.CTkFrame(self, fg_color=("gray90","gray18"),
                            corner_radius=0, height=40)
        prog.pack(fill="x")
        prog.pack_propagate(False)
        prog.grid_columnconfigure(0, weight=1)
        self._prog_lbl = ctk.CTkLabel(prog, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color=("gray50","gray55"))
        self._prog_lbl.grid(row=0, column=0, padx=14, pady=10, sticky="w")
        ctk.CTkButton(prog, text="✕ Kết thúc", width=90, height=28,
                      corner_radius=6,
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self._finish
                      ).grid(row=0, column=1, padx=14, pady=6)

        self._bar_bg   = ctk.CTkFrame(self, fg_color=("gray80","gray30"),
                                       height=4, corner_radius=0)
        self._bar_bg.pack(fill="x")
        self._bar_fill = ctk.CTkFrame(self._bar_bg, fg_color=COLOR_BLUE,
                                       height=4, corner_radius=0)
        self._bar_fill.place(relx=0, rely=0, relwidth=0, relheight=1)

        # Card display
        q_frame = ctk.CTkFrame(self, fg_color=("gray85","gray20"),
                                corner_radius=14)
        q_frame.pack(fill="x", padx=24, pady=(20,8))

        self._type_lbl = ctk.CTkLabel(q_frame, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color=("gray55","gray55"))
        self._type_lbl.pack(pady=(14,2))

        self._char_lbl = ctk.CTkLabel(
            q_frame, text="",
            font=ctk.CTkFont(family="Noto Sans JP", size=64, weight="bold"),
            text_color=("gray10","gray95"))
        self._char_lbl.pack()

        self._hint_lbl = ctk.CTkLabel(q_frame, text="",
                                       font=ctk.CTkFont(size=14),
                                       text_color=("gray50","gray55"))
        self._hint_lbl.pack(pady=(2,14))

        # Prompt label
        self._prompt_lbl = ctk.CTkLabel(self, text="",
                                         font=ctk.CTkFont(size=12, weight="bold"),
                                         text_color=("gray40","gray60"))
        self._prompt_lbl.pack(pady=(8,4))

        # Input row
        input_row = ctk.CTkFrame(self, fg_color="transparent")
        input_row.pack(fill="x", padx=24)
        input_row.grid_columnconfigure(0, weight=1)

        self._input = ctk.CTkEntry(
            input_row,
            placeholder_text="Nhập câu trả lời...",
            font=ctk.CTkFont(size=16),
            height=46)
        self._input.grid(row=0, column=0, sticky="ew", padx=(0,8))
        self._input.bind("<Return>", lambda _: self._check())

        self._submit_btn = ctk.CTkButton(
            input_row, text="✓", width=52, height=46,
            corner_radius=8,
            font=ctk.CTkFont(size=18, weight="bold"),
            command=self._check)
        self._submit_btn.grid(row=0, column=1)

        # Feedback
        self._feedback_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=13),
            wraplength=500, justify="center")
        self._feedback_lbl.pack(pady=10)

        # Skip button
        ctk.CTkButton(self, text="⏭  Bỏ qua",
                      width=100, height=30, corner_radius=6,
                      fg_color=("gray75","gray35"),
                      text_color=("gray10","gray90"),
                      font=ctk.CTkFont(size=11),
                      command=self._skip).pack(pady=(0,8))

    # ── Session logic ─────────────────────────────────────────────────────────

    def _build_session_items(self):
        """Expand self._cards into the flat list of items actually asked."""
        if self._ask_mode == "kana":
            return expand_kana_items(self._cards, self._split_readings)
        if self._ask_mode in ("on", "kun"):
            return expand_reading_items(self._cards, self._ask_mode)
        return [dict(c) for c in self._cards]

    def _start(self):
        self._session_items = self._build_session_items()
        self._queue   = self._session_items[:]
        random.shuffle(self._queue)
        self._correct = self._wrong = 0
        self._next()

    def _next(self):
        if not self._queue:
            self._finish()
            return
        self._answered = False
        self._current  = self._queue.pop(0)
        self._input.delete(0, "end")
        self._input.configure(border_color=("gray70","gray30"))
        self._feedback_lbl.configure(text="")
        self._submit_btn.configure(state="normal")
        self._render_question()
        self._update_progress()
        self.after(50, lambda: (self._input.focus_set()
                                if self.winfo_exists() else None))

    def _render_question(self):
        c = self._current
        t = c.get("type","")
        jlpt = f"  {c['jlpt_level']}" if c.get("jlpt_level") else ""
        self._type_lbl.configure(
            text=f"{TYPE_LABELS_FULL.get(t,t)}{jlpt}")
        self._char_lbl.configure(text=c["character"])

        # Hint: show part of the answer depending on mode
        hint = ""
        if self._ask_mode == "meaning":
            # Show romaji as hint
            hint = c.get("romaji","") or ""
            self._prompt_lbl.configure(
                text="Nhập nghĩa tiếng Việt:")
        elif self._ask_mode == "romaji":
            # Show first char of meaning as hint
            mv = c.get("meaning_vi","")
            hint = mv[:2] + "..." if len(mv) > 2 else mv
            self._prompt_lbl.configure(text="Nhập romaji (phiên âm Latin):")
        elif self._ask_mode == "kana":
            # Show romaji as hint
            hint = c.get("romaji","") or ""
            rtype = c.get("_reading_type")
            pos   = c.get("_reading_pos")
            label = {"on": "âm ON-yomi", "kun": "âm KUN-yomi",
                     "kana": "cách đọc"}.get(rtype, "cách đọc")
            suffix = f"  ({pos})" if pos else ""
            self._prompt_lbl.configure(text=f"Nhập {label}{suffix}:")
        elif self._ask_mode == "hanviet":
            # Show on-yomi/kana as hint (khác hệ chữ nên không lộ đáp án)
            hint = c.get("reading_kana","") or (c.get("reading_on","") or "").split("、")[0]
            self._prompt_lbl.configure(text="Nhập âm Hán Việt:")
        elif self._ask_mode in ("on", "kun"):
            # Gợi ý bằng romaji hoặc nghĩa VN — khác hệ nên không lộ đáp án
            hint = c.get("romaji","") or ""
            pos = c.get("_reading_pos")
            label = "âm ON-yomi" if self._ask_mode == "on" else "âm KUN-yomi"
            suffix = f"  ({pos})" if pos else ""
            self._prompt_lbl.configure(text=f"Nhập {label}{suffix}:")

        self._hint_lbl.configure(text=hint)

    def _check(self):
        if self._answered:
            return
        answer = self._input.get().strip()
        if not answer:
            return
        self._answered = True
        self._submit_btn.configure(state="disabled")

        correct, correct_answers = self._is_correct(answer)

        if correct:
            self._correct += 1
            self._input.configure(border_color=COLOR_GREEN)
            self._feedback_lbl.configure(
                text=f"✅  Chính xác!",
                text_color=COLOR_GREEN)
        else:
            self._wrong += 1
            self._input.configure(border_color=COLOR_RED)
            shown = " / ".join(correct_answers[:3])
            self._feedback_lbl.configure(
                text=f"❌  Sai!  Đáp án đúng: {shown}",
                text_color=COLOR_RED)
            # Re-queue near front
            insert_at = min(3, len(self._queue))
            self._queue.insert(insert_at, self._current)

        try:
            self._study_service.log_study(self._current["id"],
                      "correct" if correct else "incorrect")
        except Exception as e:
            logger.warning(f"Failed to log study result for card {self._current['id']}: {e}")

        self.after(self._NEXT_DELAY_MS,
                   lambda: (self._next() if self.winfo_exists() else None))

    def _is_correct(self, answer: str) -> tuple[bool, list]:
        """
        Flexible matching:
        - Case-insensitive
        - Strip whitespace
        - Accept any of the correct_answers list
        - Romaji: accept common variants (ou=o, uu=u, n=m before b/p)
        """
        c    = self._current
        norm = lambda s: s.strip().lower() if s else ""
        ans  = norm(answer)

        correct_answers = []
        if self._ask_mode == "meaning":
            vi = c.get("meaning_vi","")
            en = c.get("meaning_en","")
            correct_answers = [x for x in [vi, en] if x]
            # Also accept individual words (comma-separated)
            for v in [vi, en]:
                if v:
                    for part in v.replace("、","、").split(","):
                        p = part.strip()
                        if p and p not in correct_answers:
                            correct_answers.append(p)
        elif self._ask_mode == "romaji":
            romaji = c.get("romaji","")
            correct_answers = [romaji] if romaji else []
            # Auto-generate if missing
            kana = (c.get("reading_kana") or
                    c.get("reading_kun","").split("、")[0])
            if kana and not romaji:
                correct_answers.append(kana_to_romaji(kana))
        elif self._ask_mode == "kana":
            if "_reading_value" in c:
                # Split mode: this item targets exactly one reading.
                correct_answers = [c["_reading_value"]]
            else:
                # Legacy/unsplit mode: accept any on/kun/kana reading.
                kana = c.get("reading_kana","")
                kun  = c.get("reading_kun","")
                on   = c.get("reading_on","")
                for k in [kana] + (kun.split("、") if kun else []) + (on.split("、") if on else []):
                    k = k.strip()
                    if k and k not in correct_answers:
                        correct_answers.append(k)
        elif self._ask_mode == "hanviet":
            hv = c.get("reading_hanviet","")
            correct_answers = [hv] if hv else []
        elif self._ask_mode in ("on", "kun"):
            correct_answers = [c["_reading_value"]] if "_reading_value" in c else []

        normed = [norm(a) for a in correct_answers if a]

        # Direct match
        if ans in normed:
            return True, correct_answers

        # Romaji variant matching
        def normalize_romaji(s):
            return (s.replace("oo","o").replace("ou","o")
                     .replace("uu","u").replace("tt","t")
                     .replace("mb","nb").replace("mp","np"))

        if self._ask_mode in ("romaji", "meaning"):
            if normalize_romaji(ans) in [normalize_romaji(n) for n in normed]:
                return True, correct_answers

        return False, correct_answers

    def _skip(self):
        if not self._answered:
            self._wrong += 1
            c = self._current
            correct_answers = []
            if self._ask_mode == "meaning":
                correct_answers = [c.get("meaning_vi","") or c.get("meaning_en","")]
            elif self._ask_mode == "romaji":
                correct_answers = [c.get("romaji","")]
            elif self._ask_mode == "kana":
                correct_answers = [c.get("_reading_value") or
                                    c.get("reading_kana","") or c.get("reading_kun","")]
            elif self._ask_mode == "hanviet":
                correct_answers = [c.get("reading_hanviet","")]
            elif self._ask_mode in ("on", "kun"):
                correct_answers = [c.get("_reading_value","")]
            shown = " / ".join(a for a in correct_answers if a)
            self._feedback_lbl.configure(
                text=f"⏭  Đã bỏ qua.  Đáp án: {shown}",
                text_color=COLOR_GOLD)
            insert_at = min(3, len(self._queue))
            self._queue.insert(insert_at, self._current)
            try:
                self._study_service.log_study(self._current["id"], "incorrect")
            except Exception as e:
                logger.warning(f"Failed to log study result for card {self._current['id']}: {e}")
        self._next()

    def _update_progress(self):
        done  = self._correct + self._wrong
        total = len(self._session_items)
        pct   = done / total if total else 0
        acc   = round(self._correct / done * 100) if done else 0
        self._prog_lbl.configure(
            text=f"Thẻ {min(done+1,total)}/{total}   "
                 f"✓ {self._correct}   ✗ {self._wrong}"
                 + (f"   Chính xác: {acc}%" if done else ""))
        self._bar_fill.place(relwidth=pct)

    def _finish(self):
        done = self._correct + self._wrong
        acc  = round(self._correct / done * 100) if done else 0
        for w in self.winfo_children():
            w.destroy()

        ctk.CTkLabel(self, text="⌨️  Kết quả Luyện gõ",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(40,20))

        stats = ctk.CTkFrame(self, fg_color=("gray85","gray20"), corner_radius=12)
        stats.pack(padx=40, fill="x")
        for label, val, color in [
            ("✅  Đúng",         str(self._correct), COLOR_GREEN),
            ("❌  Sai / Bỏ qua", str(self._wrong),   COLOR_RED),
            ("📊  Chính xác",    f"{acc}%",           COLOR_BLUE),
            ("📚  Tổng thẻ",     str(len(self._cards)), "gray"),
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
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.destroy, height=42
                      ).pack(side="left", fill="x", expand=True, padx=(0,8))
        ctk.CTkButton(btn_row, text="🔄  Làm lại",
                      command=self._restart, height=42
                      ).pack(side="right", fill="x", expand=True, padx=(8,0))

    def _restart(self):
        for w in self.winfo_children():
            w.destroy()
        self._build()
        self._start()


# ── Launcher ──────────────────────────────────────────────────────────────────

class TypingLauncher(ctk.CTkToplevel):
    def __init__(self, master, card_service, deck_service, study_service, default_due_only=False):
        super().__init__(master)
        self._card_service  = card_service
        self._deck_service  = deck_service
        self._study_service = study_service
        self._default_due_only = default_due_only
        self.title("⌨️  Luyện gõ")
        self.geometry("420x560")
        self.minsize(420, 400)
        self.resizable(True, True)
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="⌨️  Luyện gõ",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(24,4))
        ctk.CTkLabel(self, text="Nhìn ký tự → gõ câu trả lời đúng",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55")).pack(pady=(0,16))

        # Nút Hủy / Bắt đầu pack "side=bottom" TRƯỚC vùng cuộn, để luôn
        # được dành chỗ và hiển thị ở đáy cửa sổ dù nội dung bộ lọc dài bao nhiêu.
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=24, pady=(4,24))
        ctk.CTkButton(btn_row, text="✕  Hủy",
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.destroy, height=42
                      ).pack(side="left", fill="x", expand=True, padx=(0,8))
        ctk.CTkButton(btn_row, text="▶  Bắt đầu",
                      command=self._launch, height=42
                      ).pack(side="right", fill="x", expand=True, padx=(8,0))

        self._count_lbl = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color=("gray50","gray55"))
        self._count_lbl.pack(side="bottom", pady=10)

        # Vùng bộ lọc có thể cuộn — không còn nguy cơ đẩy nút Bắt đầu ra ngoài màn hình
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=0)

        f = ctk.CTkFrame(body, fg_color=("gray88","gray20"), corner_radius=12)
        f.pack(fill="x", padx=16, pady=4)

        def row(p, label, widget_fn):
            r = ctk.CTkFrame(p, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=6)
            r.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(r, text=label, width=80,
                         font=ctk.CTkFont(size=12), anchor="w"
                         ).grid(row=0, column=0, sticky="w")
            w = widget_fn(r)
            w.grid(row=0, column=1, sticky="ew", padx=(8,0))
            return w

        self._type_var   = ctk.StringVar(value="Tất cả")
        self._jlpt_var   = ctk.StringVar(value="Tất cả")
        self._status_var = ctk.StringVar(value="Tất cả")
        self._deck_var   = ctk.StringVar(value="Tất cả")
        self._limit_var  = ctk.StringVar(value="20")
        self._mode_var   = ctk.StringVar(value="meaning")
        self._split_var  = ctk.BooleanVar(value=True)

        decks = self._deck_service.list_decks()
        self._deck_name_to_id = {d["name"]: d["id"] for d in decks}

        row(f, "Loại",   lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"]+CARD_TYPES, variable=self._type_var))
        row(f, "JLPT",   lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"]+JLPT_LEVELS, variable=self._jlpt_var))
        row(f, "Status", lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"]+CARD_STATUSES, variable=self._status_var))
        row(f, "Deck",   lambda p: ctk.CTkOptionMenu(
            p, values=["Tất cả"] + list(self._deck_name_to_id), variable=self._deck_var))
        row(f, "Số thẻ", lambda p: ctk.CTkOptionMenu(
            p, values=["10","20","30","50","Tất cả"], variable=self._limit_var))

        self._due_var = ctk.BooleanVar(value=self._default_due_only)
        due_row = ctk.CTkFrame(f, fg_color="transparent")
        due_row.pack(fill="x", padx=16, pady=(2, 4))
        due_count = self._card_service.due_count()
        due_cb = ctk.CTkCheckBox(due_row, text=f"🎯 Chỉ ôn thẻ đến hạn ({due_count})",
                         variable=self._due_var,
                         font=ctk.CTkFont(size=12))
        due_cb.pack(anchor="w")
        Tooltip(due_cb, "Chỉ lấy các thẻ đã đến lịch ôn lại (SRS), "
                        "bỏ qua thẻ vừa ôn gần đây và chưa cần ôn lại.")

        # Ask mode
        ctk.CTkLabel(f, text="Hỏi về:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(8,4))
        mode_frame = ctk.CTkFrame(f, fg_color="transparent")
        mode_frame.pack(fill="x", padx=16, pady=(0,4))
        mode_frame.grid_columnconfigure((0,1,2), weight=1)
        mode_options = [("Nghĩa VN","meaning"), ("Romaji","romaji"), ("Kana","kana"),
                        ("Hán Việt","hanviet"), ("Âm On-yomi","on"), ("Âm Kun-yomi","kun")]
        for i, (label, val) in enumerate(mode_options):
            r, c = divmod(i, 3)
            ctk.CTkRadioButton(mode_frame, text=label,
                               variable=self._mode_var, value=val,
                               command=lambda: self._update_split_visibility()
                               ).grid(row=r, column=c, sticky="w", padx=(0,8), pady=3)

        self._split_row = ctk.CTkFrame(f, fg_color="transparent")
        self._split_cb = ctk.CTkCheckBox(
            self._split_row,
            text="Tách riêng từng âm đọc (on/kun) thành câu hỏi riêng",
            variable=self._split_var,
            font=ctk.CTkFont(size=12))
        self._split_cb.pack(anchor="w")
        Tooltip(self._split_cb,
                "Bật: mỗi âm on/kun của một kanji (vd 月 → げつ、がつ、つき) "
                "là 1 câu hỏi riêng, chỉ chấp nhận đúng âm đó.\n"
                "Tắt: gõ đúng 1 trong các âm đọc của thẻ là được tính đúng cả thẻ.")
        self._split_row.pack(fill="x", padx=16, pady=(0,12))
        self._update_split_visibility()


        for v in [self._type_var, self._jlpt_var, self._status_var, self._deck_var,
                  self._limit_var, self._due_var, self._split_var]:
            v.trace_add("write", lambda *_: self._update_count())
        self._update_count()

    def _update_split_visibility(self):
        if self._mode_var.get() == "kana":
            self._split_row.pack(fill="x", padx=16, pady=(0,12))
        else:
            self._split_row.pack_forget()
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
        cards  = self._card_service.list_cards(**kw)
        mode   = self._mode_var.get()
        # Filter cards that have the required field for the chosen mode
        if mode == "meaning":
            cards = [c for c in cards if c.get("meaning_vi")]
        elif mode == "romaji":
            cards = [c for c in cards if c.get("romaji") or c.get("reading_kana")]
        elif mode == "kana":
            cards = [c for c in cards if
                     c.get("reading_kana") or c.get("reading_kun")]
        elif mode == "hanviet":
            cards = [c for c in cards if c.get("reading_hanviet")]
        elif mode in ("on", "kun"):
            cards = [c for c in cards if c.get("type") == "kanji"
                     and c.get(f"reading_{mode}")]
        limit = self._limit_var.get()
        if limit != "Tất cả":
            cards = cards[:int(limit)]
        return cards

    def _update_count(self):
        try:
            cards = self._get_cards()
            mode  = self._mode_var.get()
            if mode == "kana":
                n = len(expand_kana_items(cards, self._split_var.get()))
                label = "câu hỏi" if self._split_var.get() else "thẻ"
            elif mode in ("on", "kun"):
                n = len(expand_reading_items(cards, mode))
                label = "câu hỏi"
            else:
                n, label = len(cards), "thẻ"
            color = "#4ECB85" if n >= 1 else "#E85D5D"
            self._count_lbl.configure(text=f"Sẽ luyện {n} {label}",
                                       text_color=color)
        except Exception:
            pass

    def _launch(self):
        cards = self._get_cards()
        if not cards:
            return
        mode = self._mode_var.get()
        split = self._split_var.get()
        self.destroy()
        TypingView(self.master, cards, self._study_service, ask_mode=mode, split_readings=split)
