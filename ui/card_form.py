"""
card_form.py — Add / Edit card dialog.
_build() is split into focused sub-builders for readability.
"""
from ui.threadsafe import call_in_ui
import customtkinter as ctk
from tkinter import messagebox
from database.models import DBError
from infrastructure import jisho as jisho_api
from infrastructure import translate as translate_api
from domain.kana import kana_to_romaji
from domain.validators import validate_required, resolve_romaji_source, build_card_data, truncate, normalize_multi_reading
from ui.media_picker import MediaPicker
from constants import (
    CARD_TYPES, CARD_STATUSES, JLPT_LEVELS_OPT,
    TYPE_KANJI, TYPE_VOCAB, TYPE_HIRAGANA, TYPE_KATAKANA, STATUS_NEW,
    KB_SAVE, KB_ESCAPE, MAX_CHARACTER_LEN, MAX_MEANING_LEN,
    CARD_POS, POS_LABELS,
)
import logging

logger = logging.getLogger(__name__)


POS_NONE = "— chưa chọn —"
_POS_BY_LABEL = {v: k for k, v in POS_LABELS.items()}

class CardForm(ctk.CTkToplevel):
    def __init__(self, master, card_service, on_save, card=None, preset=None):
        super().__init__(master)
        if card is not None and not isinstance(card, dict):
            card = None
        self._card_service = card_service
        self.on_save = on_save
        self.card    = card
        self.title("✏️  Sửa thẻ" if card else "➕  Thêm thẻ mới")
        self.geometry("620x720")
        self.resizable(False, True)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.bind(KB_SAVE,   lambda _: self._save())
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        self._build()
        if card:
            self._fill(card)
        elif isinstance(preset, dict) and preset:
            self._apply_preset(preset)

    # ── Top-level builder ─────────────────────────────────────────────────────

    def _build(self):
        if not self.card:
            self._build_jisho_bar()

        # Picker frame (hidden until search results arrive)
        self._picker_frame = ctk.CTkFrame(
            self, fg_color=("gray88", "gray22"), corner_radius=0)

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True)

        self._build_type_jlpt(scroll)
        self._build_character(scroll)
        self._build_readings(scroll)       # dynamic — rebuilt on type change
        self._build_romaji(scroll)
        self._build_meanings(scroll)
        self._build_advanced(scroll)       # ví dụ, trạng thái, nguồn, media, ghi chú (thu gọn)
        self._build_buttons()
        if not self.card:
            self._wire_autofill()

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_advanced(self, scroll):
        """Phần ít dùng được thu gọn khi thêm thẻ mới (giống web: 'Tùy chọn thêm')."""
        self._adv_open = bool(self.card)
        self._adv_btn = ctk.CTkButton(
            scroll, text="", anchor="w", height=28, corner_radius=6,
            fg_color=("gray85", "gray25"), hover_color=("gray78", "gray32"),
            text_color=("gray20", "gray85"), font=ctk.CTkFont(size=12),
            command=self._toggle_adv)
        self._adv_btn.pack(fill="x", padx=20, pady=(12, 0))
        self._adv_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._build_examples(self._adv_frame)
        self._build_meta(self._adv_frame)
        self._build_media(self._adv_frame)
        self._build_notes(self._adv_frame)
        self._apply_adv()

    def _toggle_adv(self):
        self._adv_open = not self._adv_open
        self._apply_adv()

    def _apply_adv(self):
        if self._adv_open:
            self._adv_frame.pack(fill="x", after=self._adv_btn)
        else:
            self._adv_frame.pack_forget()
        self._adv_btn.configure(
            text=("▼  Tùy chọn thêm" if self._adv_open else "▶  Tùy chọn thêm")
                 + "  (ví dụ, trạng thái, nguồn, ảnh, ghi chú)")

    # ── Tự điền từ Jisho khi gõ ký tự ─────────────────────────────────────────

    def _wire_autofill(self):
        self._af_job = None
        self._af_seq = 0
        self._af_filled = set()          # tên ô do tự điền (được phép ghi đè lại)
        self.char_entry.bind("<KeyRelease>", self._af_schedule, add="+")

    def _af_schedule(self, _e=None):
        if self._af_job:
            self.after_cancel(self._af_job)
        self._af_job = self.after(650, self._af_run)

    def _af_run(self):
        self._af_job = None
        word = self.char_entry.get().strip()
        if not word or all(ord(c) < 128 for c in word):
            return                       # chỉ tra khi có ký tự Nhật
        self._af_seq += 1
        seq = self._af_seq
        jisho_api.search(word, lambda res, err: call_in_ui(
            self, lambda: self._af_apply(seq, word, res, err)))

    def _af_set(self, key, entry_widget, value):
        """Chỉ điền ô đang trống hoặc ô do tự điền trước đó."""
        if not value:
            return
        cur = entry_widget.get().strip()
        if cur and key not in self._af_filled:
            return
        entry_widget.delete(0, "end")
        entry_widget.insert(0, value)
        self._af_filled.add(key)

    def _af_apply(self, seq, word, results, error):
        if seq != self._af_seq or error or not results:
            return                       # kết quả cũ / lỗi: im lặng
        if self.char_entry.get().strip() != word:
            return
        hit = next((r for r in results
                    if isinstance(r, dict) and word in (r.get("word"), r.get("reading"))), None)
        if not hit:
            return
        reading = hit.get("reading", "")
        if self.type_var.get() != TYPE_KANJI and getattr(self, "kana_entry", None):
            self._af_set("kana", self.kana_entry, reading)
        self._af_set("en", self.meaning_en_entry, hit.get("meaning_en", "")[:MAX_MEANING_LEN])
        if reading:
            self._af_set("romaji", self.romaji_entry, kana_to_romaji(reading))
        if hit.get("jlpt") in JLPT_LEVELS_OPT and not self.jlpt_var.get():
            self.jlpt_var.set(hit["jlpt"])
        if not self.source_entry.get().strip():
            self.source_entry.insert(0, "Jisho.org")
        self._jstatus.configure(text=f"✓ Tự điền: {word}", text_color="#4ECB85")

    def _build_jisho_bar(self):
        """Search bar shown only in add mode."""
        bar = ctk.CTkFrame(self, fg_color=("gray90", "gray20"),
                           corner_radius=0, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text="🔍 Jisho:",
                     font=ctk.CTkFont(size=12, weight="bold")
                     ).grid(row=0, column=0, padx=(14, 6), pady=12, sticky="w")

        self._jsearch_var = ctk.StringVar()
        self._jsearch_entry = ctk.CTkEntry(
            bar, textvariable=self._jsearch_var,
            placeholder_text="Nhập từ tiếng Nhật hoặc nghĩa tiếng Anh...",
            height=32, font=ctk.CTkFont(family="Noto Sans JP", size=13))
        self._jsearch_entry.grid(row=0, column=0, padx=(70, 8), pady=10, sticky="ew")
        self._jsearch_entry.bind("<Return>", lambda _: self._jisho_search())

        self._jsearch_btn = ctk.CTkButton(
            bar, text="Tìm", width=60, height=32,
            command=self._jisho_search)
        self._jsearch_btn.grid(row=0, column=1, padx=(0, 8), pady=10)

        self._jstatus = ctk.CTkLabel(
            bar, text="", font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray55"))
        self._jstatus.grid(row=0, column=2, padx=(0, 12))

    def _build_type_jlpt(self, f):
        """Type selector + JLPT level row."""
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(14, 4))
        ctk.CTkLabel(row, text="🔴 Loại",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(row, text="Cấp JLPT",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w", padx=(20, 0))
        ctk.CTkLabel(row, text="Từ loại",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.type_var = ctk.StringVar(value=CARD_TYPES[0])
        self.jlpt_var = ctk.StringVar(value="")
        ctk.CTkOptionMenu(row, values=CARD_TYPES, variable=self.type_var,
                          command=self._on_type_change, width=180
                          ).grid(row=1, column=0, sticky="w")
        ctk.CTkOptionMenu(row, values=JLPT_LEVELS_OPT, variable=self.jlpt_var,
                          width=120).grid(row=1, column=1, sticky="w", padx=(20, 0))
        self.pos_var = ctk.StringVar(value=POS_NONE)
        ctk.CTkOptionMenu(row, values=[POS_NONE] + [POS_LABELS[k] for k in CARD_POS], variable=self.pos_var,
                          width=190).grid(row=1, column=2, sticky="w", padx=(20, 0))

    def _build_character(self, f):
        """Main character entry."""
        self._lbl(f, "🔴 Ký tự chính")
        self.char_entry = ctk.CTkEntry(
            f, placeholder_text="VD: 雨 / あ / ア / 食べる",
            font=ctk.CTkFont(family="Noto Sans JP", size=18))
        self.char_entry.pack(fill="x", padx=20)

    def _build_readings(self, scroll=None, prefill=None):
        """Dynamic reading fields — rebuilt when type changes.

        `prefill` is an optional card-like dict (only used when loading an
        existing card / a Jisho result) supplying reading_on/reading_kun/
        reading_kana/reading_hanviet to pre-populate the widgets. On a
        plain type change (no prefill) the fields simply reset to empty,
        matching the previous behavior.
        """
        if scroll:
            self._scroll_ref = scroll

        if not hasattr(self, "readings_frame"):
            self.readings_frame = ctk.CTkFrame(
                self._scroll_ref, fg_color="transparent")
            self.readings_frame.pack(fill="x", padx=20, pady=4)

        for w in self.readings_frame.winfo_children():
            w.destroy()

        self.on_entries = []
        self.kun_entries = []
        self.on_entry = self.kun_entry = self.kana_entry = self.hanviet_entry = None
        self.stroke_entry = None
        t = self.type_var.get()
        prefill = prefill or {}

        if t == TYPE_KANJI:
            self.readings_frame.grid_columnconfigure(0, weight=1)
            self.readings_frame.grid_columnconfigure(1, weight=1)
            self._build_multi_reading_column(
                self.readings_frame, row=0, col=0,
                label_text="Âm On-yomi", placeholder="VD: ウ",
                initial_value=prefill.get("reading_on"), entries_attr="on_entries")
            self._build_multi_reading_column(
                self.readings_frame, row=0, col=1,
                label_text="Âm Kun-yomi", placeholder="VD: あめ",
                initial_value=prefill.get("reading_kun"), entries_attr="kun_entries")
            self._build_hanviet_field(self.readings_frame, row=1, prefill=prefill)
            self._build_stroke_field(self.readings_frame, row=3, prefill=prefill)
        elif t == TYPE_VOCAB:
            ctk.CTkLabel(self.readings_frame, text="Cách đọc (Kana)",
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
            self.kana_entry = ctk.CTkEntry(
                self.readings_frame, placeholder_text="たべる", width=250,
                font=ctk.CTkFont(family="Noto Sans JP", size=14))
            self.kana_entry.grid(row=1, column=0, sticky="w", pady=(2, 0))
            if prefill.get("reading_kana"):
                self.kana_entry.insert(0, prefill["reading_kana"])
            self._build_hanviet_field(self.readings_frame, row=2, prefill=prefill)
        elif t in (TYPE_HIRAGANA, TYPE_KATAKANA):
            ctk.CTkLabel(self.readings_frame, text="Kana",
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
            self.kana_entry = ctk.CTkEntry(
                self.readings_frame, placeholder_text="あ / ア", width=250,
                font=ctk.CTkFont(family="Noto Sans JP", size=14))
            self.kana_entry.grid(row=1, column=0, sticky="w", pady=(2, 0))
            if prefill.get("reading_kana"):
                self.kana_entry.insert(0, prefill["reading_kana"])

    def _build_hanviet_field(self, parent, row, prefill=None):
        """Single-line Hán Việt reading, shown for kanji & vocab cards."""
        prefill = prefill or {}
        ctk.CTkLabel(parent, text="Hán Việt",
                     font=ctk.CTkFont(weight="bold")
                     ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.hanviet_entry = ctk.CTkEntry(
            parent, placeholder_text="VD: vũ, nguyệt",
            font=ctk.CTkFont(family="Noto Sans JP", size=14))
        self.hanviet_entry.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        if prefill.get("reading_hanviet"):
            self.hanviet_entry.insert(0, prefill["reading_hanviet"])

    def _build_stroke_field(self, parent, row, prefill=None):
        """Số nét (stroke count) — chỉ áp dụng cho thẻ Kanji."""
        prefill = prefill or {}
        ctk.CTkLabel(parent, text="Số nét",
                     font=ctk.CTkFont(weight="bold")
                     ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.stroke_entry = ctk.CTkEntry(
            parent, placeholder_text="VD: 8", width=100,
            font=ctk.CTkFont(size=14))
        self.stroke_entry.grid(row=row + 1, column=0, sticky="w", pady=(2, 0))
        sc = prefill.get("stroke_count")
        if sc:
            self.stroke_entry.insert(0, str(sc))

    # ── Dynamic multi-reading rows (On-yomi / Kun-yomi) ─────────────────────────

    def _build_multi_reading_column(self, parent, row, col, label_text,
                                     placeholder, initial_value, entries_attr):
        """
        Builds a labeled column containing one Entry per individual reading
        (instead of one Entry with readings joined by ,/、) plus a "+ Thêm
        âm đọc" button to add more rows and a "✕" per row to remove one.
        Sets self.<entries_attr> to the live list of Entry widgets.
        """
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=row, column=col, sticky="new", padx=(0 if col == 0 else 16, 0))
        ctk.CTkLabel(wrap, text=label_text,
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        rows_container = ctk.CTkFrame(wrap, fg_color="transparent")
        rows_container.pack(fill="x")

        entries = getattr(self, entries_attr)
        initial_parts = [p for p in normalize_multi_reading(initial_value or "").split("、") if p] or [""]
        for part in initial_parts:
            self._add_reading_entry(rows_container, entries, placeholder, part)

        ctk.CTkButton(
            wrap, text="+ Thêm âm đọc", width=110, height=24, corner_radius=6,
            font=ctk.CTkFont(size=11),
            fg_color=("gray80", "gray30"), text_color=("gray10", "gray90"),
            command=lambda: self._add_reading_entry(rows_container, entries, placeholder)
        ).pack(anchor="w", pady=(3, 0))

    def _add_reading_entry(self, container, entries_list, placeholder, initial=""):
        """Add one reading row (Entry + ✕ remove button) to a rows container."""
        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", pady=(0, 3))
        entry = ctk.CTkEntry(row, placeholder_text=placeholder,
                              font=ctk.CTkFont(family="Noto Sans JP", size=13))
        entry.pack(side="left", fill="x", expand=True)
        if initial:
            entry.insert(0, initial)
        ctk.CTkButton(
            row, text="✕", width=24, height=24, corner_radius=4,
            fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
            hover_color=("gray65", "gray45"),
            command=lambda: self._remove_reading_entry(row, entry, entries_list, container, placeholder)
        ).pack(side="left", padx=(4, 0))
        entries_list.append(entry)
        return entry

    def _remove_reading_entry(self, row, entry, entries_list, container, placeholder):
        """Remove one reading row; always keep at least one empty row present."""
        if entry in entries_list:
            entries_list.remove(entry)
        row.destroy()
        if not entries_list:
            self._add_reading_entry(container, entries_list, placeholder)

    def _get_multi_reading_value(self, entries_list) -> str:
        """Join the non-empty rows of a dynamic reading list into the
        canonical "、"-separated string stored in the DB."""
        values = [e.get().strip() for e in entries_list if e.get().strip()]
        return "、".join(values)

    def _build_romaji(self, f):
        """Romaji entry with auto-generate button."""
        self._lbl(f, "Romaji")
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=20)
        row.grid_columnconfigure(0, weight=1)
        self.romaji_entry = ctk.CTkEntry(row, placeholder_text="VD: ame / taberu")
        self.romaji_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(row, text="⚡ Tự tạo", width=80, height=30,
                      corner_radius=6,
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      font=ctk.CTkFont(size=11),
                      command=self._auto_romaji
                      ).grid(row=0, column=1, padx=(6, 0))

    def _build_meanings(self, f):
        """Meaning fields (Vietnamese + English)."""
        self._lbl(f, "🔴 Nghĩa tiếng Việt")
        self.meaning_vi_entry = ctk.CTkEntry(f, placeholder_text="VD: mưa")
        self.meaning_vi_entry.pack(fill="x", padx=20)

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(4, 0))
        self._translate_btn = ctk.CTkButton(
            row, text="💡 Gợi ý dịch từ nghĩa Anh", height=24,
            fg_color=("gray80", "gray28"), text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=11), command=self._suggest_translation)
        self._translate_btn.pack(side="left")
        self._translate_status = ctk.CTkLabel(
            row, text="", font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray55"), anchor="w")
        self._translate_status.pack(side="left", padx=(8, 0), fill="x", expand=True)

        self._lbl(f, "Nghĩa tiếng Anh")
        self.meaning_en_entry = ctk.CTkEntry(f, placeholder_text="VD: rain")
        self.meaning_en_entry.pack(fill="x", padx=20)

    def _build_examples(self, f):
        """Example sentence fields."""
        self._lbl(f, "Câu ví dụ (JP)")
        self.example_jp_entry = ctk.CTkEntry(
            f, placeholder_text="VD: 雨が降る",
            font=ctk.CTkFont(family="Noto Sans JP", size=13))
        self.example_jp_entry.pack(fill="x", padx=20)
        self._lbl(f, "Câu ví dụ (VI)")
        self.example_vi_entry = ctk.CTkEntry(f, placeholder_text="VD: Trời đang mưa")
        self.example_vi_entry.pack(fill="x", padx=20)

    @staticmethod
    def _status_text(status, count):
        from constants import STATUS_LABELS
        return f"{STATUS_LABELS.get(status, status)} · {count} lần học"

    def _build_meta(self, f):
        """Status, source, and favorite fields."""
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(10, 4))
        ctk.CTkLabel(row, text="Trạng thái",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(row, text="Nguồn",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w", padx=(20, 0))
        self.status_var = ctk.StringVar(value="new")      # chỉ hiển thị: trạng thái tự tính theo số lần học khi ôn tập
        self._status_lbl = ctk.CTkLabel(row, text=self._status_text("new", 0), anchor="w", width=150)
        self._status_lbl.grid(row=1, column=0, sticky="w")
        self.source_entry = ctk.CTkEntry(row, placeholder_text="Sách, anime...", width=220)
        self.source_entry.grid(row=1, column=1, sticky="w", padx=(20, 0))

        self.fav_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(f, text="⭐  Đánh dấu yêu thích",
                        variable=self.fav_var).pack(anchor="w", padx=20, pady=(10, 4))

    def _build_media(self, f):
        """Optional audio pronunciation + illustration image."""
        self._lbl(f, "Âm thanh & Ảnh minh họa (tùy chọn)")
        card = self.card if isinstance(self.card, dict) else {}
        self._media_picker = MediaPicker(
            f, audio_path=card.get("audio_path"), image_path=card.get("image_path"))
        self._media_picker.pack(fill="x", padx=20, pady=(0, 8))

    def _build_notes(self, f):
        """Notes textbox."""
        self._lbl(f, "Ghi chú cá nhân")
        self.notes_text = ctk.CTkTextbox(f, height=70)
        self.notes_text.pack(fill="x", padx=20)

    def _build_buttons(self):
        """Save / Cancel buttons at the bottom."""
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(btns, text="✕  Hủy",
                      fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy, width=100).pack(side="left")
        ctk.CTkButton(btns, text="💾  Lưu thẻ  (Ctrl+S)",
                      command=self._save, height=38).pack(side="right")
        if not self.card:
            # Only for "add new" — editing an existing card is a one-off action.
            ctk.CTkButton(btns, text="💾+  Lưu & Thêm tiếp",
                          fg_color=("gray70", "gray40"),
                          command=self._save_and_continue, height=38
                          ).pack(side="right", padx=(0, 8))

    # ── Helper ────────────────────────────────────────────────────────────────

    def _lbl(self, parent, text: str):
        """Shorthand for a section label."""
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(weight="bold"), anchor="w"
                     ).pack(fill="x", padx=20, pady=(8, 2))

    def _on_type_change(self, _=None):
        self._build_readings()

    # ── Romaji auto-generate ──────────────────────────────────────────────────

    def _auto_romaji(self):
        kana = resolve_romaji_source(
            card_type=self.type_var.get(),
            on_reading=self._get_multi_reading_value(self.on_entries) if self.on_entries else "",
            kun_reading=self._get_multi_reading_value(self.kun_entries) if self.kun_entries else "",
            kana_reading=self.kana_entry.get().strip() if self.kana_entry else "",
            character=self.char_entry.get().strip(),
        )
        if kana:
            self.romaji_entry.delete(0, "end")
            self.romaji_entry.insert(0, kana_to_romaji(kana))

    # ── Translation suggestion (EN → VI, for meaning_vi) ────────────────────────

    def _suggest_translation(self):
        en_text = self.meaning_en_entry.get().strip()
        if not en_text:
            self._translate_status.configure(
                text="Cần có nghĩa tiếng Anh trước đã", text_color=("gray50", "gray55"))
            return
        self._translate_btn.configure(state="disabled")
        self._translate_status.configure(text="Đang dịch...", text_color=("gray50", "gray55"))
        self._translate_status.unbind("<Button-1>")
        translate_api.suggest_vi(en_text, self._on_translate_result)

    def _on_translate_result(self, translation, error):
        call_in_ui(self, lambda: self._show_translate_result(translation, error))

    def _show_translate_result(self, translation, error):
        self._translate_btn.configure(state="normal")
        if error:
            self._translate_status.configure(text=f"❌ {error[:40]}", text_color="#E85D5D")
            return
        if not translation:
            self._translate_status.configure(text="Không có gợi ý", text_color=("gray50", "gray55"))
            return
        # Suggestion only — user must click it to actually fill meaning_vi.
        self._translate_status.configure(
            text=f'💡 "{translation}"  (bấm để dùng)', text_color="#4A9EFF", cursor="hand2")
        self._translate_status.bind(
            "<Button-1>", lambda _e, t=translation: self._accept_translation(t))

    def _accept_translation(self, translation: str):
        self.meaning_vi_entry.delete(0, "end")
        self.meaning_vi_entry.insert(0, translation)
        self.meaning_vi_entry.configure(border_color=("gray70", "gray30"))
        self._translate_status.configure(text="✓ Đã điền", text_color="#4ECB85", cursor="")
        self._translate_status.unbind("<Button-1>")

    # ── Jisho search ──────────────────────────────────────────────────────────

    def _jisho_search(self):
        kw = self._jsearch_var.get().strip()
        if not kw:
            return
        self._jsearch_btn.configure(state="disabled", text="...")
        self._jstatus.configure(text="Đang tìm...", text_color=("gray50", "gray55"))
        self._hide_picker()
        jisho_api.search(kw, self._on_jisho_result)

    def _on_jisho_result(self, results, error):
        call_in_ui(self, lambda: self._show_jisho_results(results, error))

    def _show_jisho_results(self, results, error):
        self._jsearch_btn.configure(state="normal", text="Tìm")
        if error:
            self._jstatus.configure(text=f"❌ {error[:50]}", text_color="#E85D5D")
            return
        if not results:
            self._jstatus.configure(text="Không tìm thấy", text_color=("gray50", "gray55"))
            return
        self._jstatus.configure(text=f"✓ {len(results)} kết quả", text_color="#4ECB85")
        self._show_picker(results)

    def _show_picker(self, results):
        self._hide_picker()
        children = self.winfo_children()
        self._picker_frame.pack(fill="x", after=children[0] if children else None)

        hdr = ctk.CTkFrame(self._picker_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(hdr, text="Chọn kết quả từ Jisho:",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkButton(hdr, text="✕", width=22, height=22,
                      fg_color="transparent", hover_color=("gray80", "gray30"),
                      text_color=("gray30", "gray80"),
                      command=self._hide_picker).pack(side="right")

        scroll = ctk.CTkScrollableFrame(self._picker_frame,
                                         fg_color="transparent", height=120)
        scroll.pack(fill="x", padx=8, pady=(0, 8))
        for r in results:
            word    = r.get("word", "")
            reading = r.get("reading", "")
            meaning = r.get("meaning_en", "")[:40]
            jlpt    = f"  [{r['jlpt']}]" if r.get("jlpt") else ""
            common  = "  ★" if r.get("is_common") else ""
            label   = f"{word}  {reading}  —  {meaning}{jlpt}{common}"
            ctk.CTkButton(
                scroll, text=label, anchor="w", height=28, corner_radius=6,
                fg_color="transparent", hover_color=("gray80", "gray28"),
                text_color=("gray10", "gray90"),
                font=ctk.CTkFont(family="Noto Sans JP", size=11),
                command=lambda entry=r: self._fill_from_jisho(entry)
            ).pack(fill="x", pady=1, padx=4)

    def _hide_picker(self):
        self._picker_frame.pack_forget()
        for w in self._picker_frame.winfo_children():
            w.destroy()

    def _fill_from_jisho(self, entry: dict):
        if not isinstance(entry, dict):
            return
        self._hide_picker()
        word      = entry.get("word", "")
        reading   = entry.get("reading", "")
        meaning   = entry.get("meaning_en", "")
        jlpt      = entry.get("jlpt", "")
        card_type = jisho_api.guess_type(entry)

        self.type_var.set(card_type)
        self.char_entry.delete(0, "end")
        self.char_entry.insert(0, word)

        raw      = entry.get("raw", {}) if isinstance(entry.get("raw"), dict) else {}
        japanese = raw.get("japanese", [])

        if card_type == TYPE_KANJI and japanese:
            on_r  = [j.get("reading","") for j in japanese
                     if isinstance(j, dict) and
                     any('\u30A0' <= c <= '\u30FF' for c in j.get("reading",""))]
            kun_r = [j.get("reading","") for j in japanese
                     if isinstance(j, dict) and
                     any('\u3040' <= c <= '\u309F' for c in j.get("reading",""))]
            self._build_readings(prefill={
                "reading_on":  "、".join(on_r) if on_r else reading,
                "reading_kun": "、".join(kun_r) if kun_r else "",
            })
        else:
            self._build_readings()
            if self.kana_entry:
                self.kana_entry.delete(0, "end")
                self.kana_entry.insert(0, reading)

        if reading:
            self.romaji_entry.delete(0, "end")
            self.romaji_entry.insert(0, kana_to_romaji(reading))

        self.meaning_en_entry.delete(0, "end")
        self.meaning_en_entry.insert(0, meaning)

        if jlpt in JLPT_LEVELS_OPT:
            self.jlpt_var.set(jlpt)

        self.source_entry.delete(0, "end")
        self.source_entry.insert(0, "Jisho.org")
        self.meaning_vi_entry.focus_set()
        self._jstatus.configure(text=f"✓ Đã điền: {word}", text_color="#4ECB85")

    def _apply_preset(self, p: dict):
        """Thêm thẻ mới nhưng điền sẵn (vd từ bài đọc Bản dịch): chữ, nghĩa, câu ví dụ, nguồn; tự tra Jisho cho từ đó."""
        self._fill({k: v for k, v in p.items() if k not in ("status", "study_count")})
        if p.get("example_jp") or p.get("source"):
            self._adv_open = True
            self._apply_adv()
        if p.get("character") and not p.get("meaning_vi"):
            try:
                self._jsearch_var.set(p["character"]); self._jisho_search()
            except Exception:
                pass
        (self.meaning_vi_entry if not p.get("meaning_vi") else self.char_entry).focus_set()

    # ── Fill existing card (edit mode) ────────────────────────────────────────

    def _fill(self, c: dict):
        if not isinstance(c, dict):
            return
        self.type_var.set(c.get("type", TYPE_VOCAB))
        self._build_readings(prefill=c)
        self.jlpt_var.set(c.get("jlpt_level") or "")
        self.pos_var.set(POS_LABELS.get(c.get("pos"), POS_NONE))
        self.char_entry.insert(0, c.get("character", ""))
        self.romaji_entry.insert(0, c.get("romaji", "") or "")
        self.meaning_vi_entry.insert(0, c.get("meaning_vi", "") or "")
        self.meaning_en_entry.insert(0, c.get("meaning_en", "") or "")
        self.example_jp_entry.insert(0, c.get("example_jp", "") or "")
        self.example_vi_entry.insert(0, c.get("example_vi", "") or "")
        self.status_var.set(c.get("status", "new"))
        self._status_lbl.configure(text=self._status_text(c.get("status", "new"), c.get("study_count") or 0))
        self.source_entry.insert(0, c.get("source", "") or "")
        self.fav_var.set(bool(c.get("is_favorite", 0)))
        if c.get("notes"):
            self.notes_text.insert("1.0", c["notes"])

    # ── Save ──────────────────────────────────────────────────────────────────

    def _get_stroke_count(self):
        """Đọc số nét từ ô nhập (chỉ tồn tại với thẻ Kanji). Trả None nếu
        trống hoặc không phải số hợp lệ."""
        entry = getattr(self, "stroke_entry", None)
        if not entry:
            return None
        val = entry.get().strip()
        if not val:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    def _save(self):
        self._do_save(close_after=True)

    def _save_and_continue(self):
        self._do_save(close_after=False)

    def _do_save(self, close_after: bool):
        char = self.char_entry.get().strip()
        vi   = self.meaning_vi_entry.get().strip()
        self.char_entry.configure(border_color=("gray70", "gray30"))
        self.meaning_vi_entry.configure(border_color=("gray70", "gray30"))

        check = validate_required(char, vi)
        if not check["valid"]:
            if not check["character"]: self.char_entry.configure(border_color="red")
            if not check["meaning_vi"]: self.meaning_vi_entry.configure(border_color="red")
            return

        char = truncate(char, MAX_CHARACTER_LEN)
        vi   = truncate(vi, MAX_MEANING_LEN)

        card_type  = self.type_var.get()
        exclude_id = self.card.get("id") if isinstance(self.card, dict) else None
        try:
            dupes = self._card_service.check_duplicates(char, card_type, exclude_id=exclude_id)
        except DBError:
            dupes = []

        if dupes:
            d = dupes[0]
            if not messagebox.askyesno("Trùng lặp",
                    f'Thẻ "{char}" ({card_type}) đã tồn tại!\n\n'
                    f'  ID: {d.get("id")}  Nghĩa: {d.get("meaning_vi","—")}\n\n'
                    f'Vẫn muốn lưu thêm bản này?', parent=self):
                return

        audio_path, image_path = self._media_picker.get_paths()
        data = build_card_data(
            card_type=card_type,
            character=char,
            meaning_vi=vi,
            reading_on=self._get_multi_reading_value(self.on_entries) if self.on_entries else None,
            reading_kun=self._get_multi_reading_value(self.kun_entries) if self.kun_entries else None,
            reading_kana=self.kana_entry.get().strip() if self.kana_entry else None,
            reading_hanviet=self.hanviet_entry.get().strip() if self.hanviet_entry else None,
            romaji=self.romaji_entry.get().strip(),
            meaning_en=self.meaning_en_entry.get().strip(),
            example_jp=self.example_jp_entry.get().strip(),
            example_vi=self.example_vi_entry.get().strip(),
            stroke_count=self._get_stroke_count(),
            jlpt_level=self.jlpt_var.get(),
            pos=_POS_BY_LABEL.get(self.pos_var.get()),
            status=self.status_var.get(),     # chỉ dùng khi thêm thẻ mới (=new); sửa thẻ không đổi trạng thái
            is_favorite=self.fav_var.get(),
            source=self.source_entry.get().strip(),
            notes=self.notes_text.get("1.0", "end-1c").strip(),
            audio_path=audio_path,
            image_path=image_path,
        )
        self.on_save(data)

        if close_after:
            self.destroy()
        else:
            self._reset_for_next()

    def _reset_for_next(self):
        """
        Clear the form for the next card after "Lưu & Thêm tiếp" — keeps
        the selected card type (bulk entry is almost always one type at a
        time) and JLPT level (also tends to repeat), clears everything else.
        """
        self.char_entry.delete(0, "end")
        self.meaning_vi_entry.delete(0, "end")
        self.meaning_en_entry.delete(0, "end")
        self.romaji_entry.delete(0, "end")
        self.example_jp_entry.delete(0, "end")
        self.example_vi_entry.delete(0, "end")
        self.source_entry.delete(0, "end")
        self.notes_text.delete("1.0", "end")
        self.fav_var.set(False)
        self.status_var.set(STATUS_NEW)

        self._build_readings()   # rebuilds on/kun/kana/hanviet/stroke fields empty
        self._media_picker.reset()
        self._translate_status.configure(text="", cursor="")
        self._translate_status.unbind("<Button-1>")

        if hasattr(self, "_jsearch_var"):
            self._jsearch_var.set("")
        self._hide_picker()

        self.char_entry.focus_set()
