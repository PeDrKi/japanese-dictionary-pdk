import customtkinter as ctk
import os
import logging
from tkinter import messagebox
from ui.tooltip import Tooltip
from infrastructure.media import open_with_default_app
from domain.srs_display import format_due_info, format_ease_label
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

STATUS_COLOR = {"new": "#6B8CFF", "learning": "#F0B429", "known": "#4ECB85"}
TYPE_LABEL   = {"kanji": "漢字", "hiragana": "ひらがな", "katakana": "カタカナ", "vocab": "語彙"}

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

logger = logging.getLogger(__name__)


class CardDetail(ctk.CTkFrame):
    """
    Right-side panel that shows full card details.
    Shown/hidden by TableView when a row is selected.
    """

    def __init__(self, master, deck_service, on_edit=None, on_delete=None, on_toggle_fav=None, **kwargs):
        super().__init__(master, corner_radius=0, width=300, **kwargs)
        self._deck_service  = deck_service
        self.on_edit       = on_edit
        self.on_delete     = on_delete
        self.on_toggle_fav = on_toggle_fav
        self._card         = None
        self.grid_propagate(False)
        self._build()
        self._show_empty()

    # ── Build skeleton ────────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Header bar ──
        hdr = ctk.CTkFrame(self, corner_radius=0,
                           fg_color=("gray90", "gray18"), height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(0, weight=1)

        self._title_lbl = ctk.CTkLabel(hdr, text="Chi tiết thẻ",
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       anchor="w")
        self._title_lbl.grid(row=0, column=0, padx=16, pady=14, sticky="w")

        btn_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_frame.grid(row=0, column=1, padx=10)

        self._fav_btn = ctk.CTkButton(
            btn_frame, text="☆", width=32, height=32, corner_radius=16,
            fg_color="transparent", hover_color=("gray80", "gray30"),
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=16), command=self._toggle_fav)
        self._fav_btn.pack(side="left", padx=2)

        _edit_btn = ctk.CTkButton(btn_frame, text="✏️", width=32, height=32, corner_radius=16,
                      fg_color="transparent", hover_color=("gray80", "gray30"),
                      text_color=("gray10", "gray90"),
                      font=ctk.CTkFont(size=14),
                      command=lambda: self.on_edit(self._card) if self.on_edit and self._card else None)
        _edit_btn.pack(side="left", padx=2)
        Tooltip(_edit_btn, "Sửa thẻ  (Double-click)")

        _del_btn = ctk.CTkButton(btn_frame, text="🗑️", width=32, height=32, corner_radius=16,
                      fg_color="transparent", hover_color=("gray80", "gray30"),
                      text_color=("gray10", "gray90"),
                      font=ctk.CTkFont(size=14),
                      command=lambda: self.on_delete(self._card) if self.on_delete and self._card else None)
        _del_btn.pack(side="left", padx=2)
        Tooltip(_del_btn, "Xóa thẻ  (Delete)")

        _deck_btn = ctk.CTkButton(btn_frame, text="📁", width=32, height=32, corner_radius=16,
                      fg_color="transparent", hover_color=("gray80", "gray30"),
                      text_color=("gray10", "gray90"),
                      font=ctk.CTkFont(size=14),
                      command=self._open_deck_assign)
        _deck_btn.pack(side="left", padx=2)

        # Tooltips for header buttons
        Tooltip(self._fav_btn, "Toggle yêu thích")
        Tooltip(_deck_btn,     "Quản lý Deck — thêm/bỏ thẻ khỏi bộ thẻ")

        # ── Scrollable body ──
        self._scroll = ctk.CTkScrollableFrame(self, corner_radius=0,
                                               fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")

    # ── Public API ────────────────────────────────────────────────────────────

    def load_card(self, card: dict):
        self._card = card
        self._render(card)

    def clear(self):
        self._card = None
        self._show_empty()

    # ── Render ────────────────────────────────────────────────────────────────

    def _show_empty(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._title_lbl.configure(text="Chi tiết thẻ")
        self._fav_btn.configure(text="☆")
        ctk.CTkLabel(self._scroll,
                     text="← Chọn một thẻ\nđể xem chi tiết",
                     font=ctk.CTkFont(size=13),
                     text_color=("gray60", "gray50"),
                     justify="center").pack(expand=True, pady=80)

    def _render(self, c: dict):
        """Orchestrate all render sub-sections."""
        for w in self._scroll.winfo_children():
            w.destroy()
        self._render_header(c)
        self._render_character(c)
        self._render_readings(c)
        self._render_meanings(c)
        self._render_examples(c)
        self._render_media(c)
        self._render_srs(c)
        self._render_decks(c)
        self._render_info(c)
        self._render_notes(c)
        # Bottom padding
        ctk.CTkFrame(self._scroll, height=24, fg_color="transparent").pack()

    def _render_header(self, c: dict):
        """Update the title label and favorite button."""
        self._title_lbl.configure(
            text=TYPE_LABEL.get(c["type"], c["type"]))
        self._fav_btn.configure(
            text="★" if c.get("is_favorite") else "☆",
            text_color="#F0B429" if c.get("is_favorite") else ("gray60","gray50"))

    def _render_character(self, c: dict):
        """Big character box with status + JLPT badges."""
        f = self._scroll
        char_frame = ctk.CTkFrame(f, fg_color=("gray85","gray20"), corner_radius=12)
        char_frame.pack(fill="x", padx=16, pady=(16,8))

        ctk.CTkLabel(char_frame, text=c["character"],
                     font=ctk.CTkFont(family="Noto Sans JP", size=64, weight="bold"),
                     text_color=("gray10","gray95")).pack(pady=(20,4))

        status  = c.get("status","new")
        s_color = STATUS_COLOR.get(status, "#6B7280")
        ctk.CTkLabel(char_frame, text=f"  {status.upper()}  ",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     fg_color=s_color, corner_radius=8,
                     text_color="white").pack(pady=(0,8))

        if c.get("jlpt_level"):
            ctk.CTkLabel(char_frame, text=c["jlpt_level"],
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=("#F0B429","#F0B429")).pack(pady=(0,16))
        else:
            ctk.CTkFrame(char_frame, height=16, fg_color="transparent").pack()

    def _render_readings(self, c: dict):
        """Reading section — varies by card type."""
        f = self._scroll
        t = c.get("type")
        if t == TYPE_KANJI:
            self._section(f, "📖 Cách đọc")
            if c.get("reading_on"):
                self._row(f, "On-yomi (音)", c["reading_on"],  color="#9B7FE8")
            if c.get("reading_kun"):
                self._row(f, "Kun-yomi (訓)", c["reading_kun"], color="#3ECFCF")
            if c.get("reading_hanviet"):
                self._row(f, "Hán Việt", c["reading_hanviet"], color="#F0B429")
            if c.get("romaji"):
                self._row(f, "Romaji", c["romaji"])
        elif t in (TYPE_HIRAGANA, TYPE_KATAKANA):
            self._section(f, "📖 Phiên âm")
            if c.get("reading_kana"):
                self._row(f, "Kana",   c["reading_kana"])
            if c.get("romaji"):
                self._row(f, "Romaji", c["romaji"])
        elif t == TYPE_VOCAB:
            self._section(f, "📖 Cách đọc")
            if c.get("reading_kana"):
                self._row(f, "Furigana", c["reading_kana"],
                          color="#3ECFCF", big=True)
            if c.get("reading_hanviet"):
                self._row(f, "Hán Việt", c["reading_hanviet"], color="#F0B429")
            if c.get("romaji"):
                self._row(f, "Romaji", c["romaji"])

    def _render_meanings(self, c: dict):
        """Vietnamese and English meanings."""
        f = self._scroll
        self._section(f, "💬 Nghĩa")
        if c.get("meaning_vi"):
            self._row(f, "Tiếng Việt", c["meaning_vi"], color="#4ECB85", big=True)
        if c.get("meaning_en"):
            self._row(f, "Tiếng Anh",  c["meaning_en"])

    def _render_examples(self, c: dict):
        """Example sentence box."""
        if not c.get("example_jp") and not c.get("example_vi"):
            return
        f = self._scroll
        self._section(f, "📝 Ví dụ")
        ex_frame = ctk.CTkFrame(f, fg_color=("gray88","gray22"), corner_radius=8)
        ex_frame.pack(fill="x", padx=16, pady=4)
        if c.get("example_jp"):
            ctk.CTkLabel(ex_frame, text=c["example_jp"],
                         font=ctk.CTkFont(family="Noto Sans JP", size=15),
                         wraplength=240, justify="left",
                         anchor="w").pack(fill="x", padx=14, pady=(10,4))
        if c.get("example_vi"):
            ctk.CTkLabel(ex_frame, text=c["example_vi"],
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50","gray55"),
                         wraplength=240, justify="left",
                         anchor="w").pack(fill="x", padx=14, pady=(0,10))

    def _render_media(self, c: dict):
        """Illustration image (if any) + play-audio button (if any)."""
        image_path = c.get("image_path")
        audio_path = c.get("audio_path")
        if not image_path and not audio_path:
            return

        f = self._scroll
        self._section(f, "🖼️  Media")

        if image_path:
            if not os.path.exists(image_path):
                ctk.CTkLabel(f, text="⚠️ File ảnh không tồn tại",
                             font=ctk.CTkFont(size=11),
                             text_color=("gray50", "gray55")).pack(padx=16, pady=4, anchor="w")
            elif not _PIL_AVAILABLE:
                ctk.CTkLabel(f, text="⚠️ Cần cài Pillow để xem ảnh (pip install Pillow)",
                             font=ctk.CTkFont(size=11),
                             text_color=("gray50", "gray55")).pack(padx=16, pady=4, anchor="w")
            else:
                try:
                    img = Image.open(image_path)
                    img.thumbnail((240, 240))
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    lbl = ctk.CTkLabel(f, image=ctk_img, text="")
                    lbl.image = ctk_img  # keep a reference — CTkImage is GC'd otherwise
                    lbl.pack(padx=16, pady=(4, 8))
                except Exception as e:
                    logger.warning(f"Could not load image {image_path}: {e}")
                    ctk.CTkLabel(f, text="⚠️ Không tải được ảnh",
                                 font=ctk.CTkFont(size=11),
                                 text_color=("gray50", "gray55")).pack(padx=16, pady=4, anchor="w")

        if audio_path:
            ctk.CTkButton(f, text="🔊  Phát âm thanh", height=32,
                          command=lambda p=audio_path: self._play_audio(p)
                          ).pack(padx=16, pady=(4, 8), anchor="w")

    def _play_audio(self, path):
        ok, msg = open_with_default_app(path)
        if not ok:
            messagebox.showerror("Lỗi phát âm thanh", msg)

    def _render_srs(self, c: dict):
        """Spaced-repetition status: when this card is next due + how easy it is."""
        if "srs_due_date" not in c:
            return  # lightweight dict without SRS columns (shouldn't happen, but be safe)
        f = self._scroll
        self._section(f, "🎯  Ôn tập ngắt quãng (SRS)")
        self._row(f, "Trạng thái", format_due_info(c.get("srs_due_date")))
        self._row(f, "Độ dễ",      format_ease_label(c.get("srs_ease")))

    def _render_decks(self, c: dict):
        """Show every deck this card belongs to (a card can be in several)."""
        if "id" not in c:
            return
        rows = self._deck_service.get_decks_for_card(c["id"])

        f = self._scroll
        self._section(f, "📁  Bộ thẻ")
        if not rows:
            ctk.CTkLabel(f, text="Chưa thuộc bộ thẻ nào",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray55", "gray55"),
                         anchor="w").pack(fill="x", padx=16, pady=(0, 4))
            return
        for d in rows:
            ctk.CTkLabel(f, text=f"{d['icon']}  {d['name']}",
                         font=ctk.CTkFont(size=12),
                         anchor="w").pack(fill="x", padx=16, pady=1)

    def _render_info(self, c: dict):
        """Stroke count, source, date added."""
        extras = []
        if c.get("stroke_count"):
            extras.append(("✏️  Số nét",    str(c["stroke_count"])))
        if c.get("source"):
            extras.append(("📚  Nguồn",     c["source"]))
        if c.get("created_at"):
            extras.append(("📅  Ngày thêm", c["created_at"][:10]))
        if not extras:
            return
        f = self._scroll
        self._section(f, "ℹ️  Thông tin")
        for label, val in extras:
            self._row(f, label, val)

    def _render_notes(self, c: dict):
        """Personal notes box."""
        if not c.get("notes"):
            return
        f = self._scroll
        self._section(f, "🗒️  Ghi chú cá nhân")
        note_frame = ctk.CTkFrame(f, fg_color=("gray88","gray22"), corner_radius=8)
        note_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(note_frame, text=c["notes"],
                     font=ctk.CTkFont(size=11),
                     text_color=("gray40","gray65"),
                     wraplength=240, justify="left",
                     anchor="w").pack(fill="x", padx=14, pady=10)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("gray50", "gray55"),
                     anchor="w").pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkFrame(parent, height=1,
                     fg_color=("gray80", "gray30")).pack(fill="x", padx=16, pady=(0, 4))

    def _row(self, parent, label, value, color=None, big=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=label,
                     font=ctk.CTkFont(size=10),
                     text_color=("gray55", "gray55"),
                     width=90, anchor="w").grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(row, text=str(value),
                     font=ctk.CTkFont(
                         family="Noto Sans JP" if any(ord(c) > 127 for c in str(value)) else None,
                         size=14 if big else 12,
                         weight="bold" if big else "normal"),
                     text_color=color if color else ("gray15", "gray90"),
                     wraplength=160, justify="left",
                     anchor="w").grid(row=0, column=1, sticky="w")

    def _open_deck_assign(self):
        if not self._card:
            return
        from ui.card_detail import DeckAssignDialog
        DeckAssignDialog(self, self._deck_service, card=self._card,
                         on_done=self._on_deck_done)

    def _on_deck_done(self):
        # Notify sidebar to refresh deck counts
        root = self.winfo_toplevel()
        if hasattr(root, "sidebar"):
            root.sidebar.refresh_decks()
            root.sidebar.refresh_stats()
        # Refresh the deck badges shown in this panel right away
        if self._card:
            self._render(self._card)

    def _toggle_fav(self):
        if self._card and self.on_toggle_fav:
            self.on_toggle_fav(self._card)
            # Optimistic UI update
            new_fav = not self._card.get("is_favorite")
            self._card["is_favorite"] = 1 if new_fav else 0
            self._fav_btn.configure(
                text="★" if new_fav else "☆",
                text_color="#F0B429" if new_fav else ("gray60", "gray50"))


# ── Deck assignment dialog ────────────────────────────────────────────────────

class DeckAssignDialog(ctk.CTkToplevel):
    """Let user add/remove the current card from any deck."""

    def __init__(self, master, deck_service, card: dict, on_done=None):
        super().__init__(master)
        self._deck_service = deck_service
        self.card    = card
        self.on_done = on_done
        self.title(f"Quản lý Deck — {card['character']}")
        self.geometry("360x440")
        self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text=f"Thẻ:  {self.card['character']}  —  {self.card.get('meaning_vi','')}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(16,4))
        ctk.CTkLabel(self, text="Chọn bộ thẻ để thêm/bỏ thẻ này:",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55"),
                     anchor="w").pack(fill="x", padx=16, pady=(0,10))

        ctk.CTkFrame(self, height=1, fg_color=("gray80","gray30")).pack(fill="x", padx=16)

        # Get current deck memberships
        member_ids = {d["id"] for d in self._deck_service.get_decks_for_card(self.card["id"])}

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        self._vars = {}
        for deck in self._deck_service.list_decks():
            var = ctk.BooleanVar(value=(deck["id"] in member_ids))
            self._vars[deck["id"]] = var
            row = ctk.CTkFrame(scroll, fg_color=("gray88","gray22"), corner_radius=8)
            row.pack(fill="x", pady=3, padx=4)
            ctk.CTkCheckBox(
                row,
                text=f"{deck['icon']}  {deck['name']}  ({deck['card_count']} thẻ)",
                font=ctk.CTkFont(size=12),
                variable=var
            ).pack(anchor="w", padx=12, pady=10)

        # Buttons
        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(btn_f, text="✕  Hủy",
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.destroy, width=100).pack(side="left")
        ctk.CTkButton(btn_f, text="💾  Lưu",
                      command=self._save, height=36).pack(side="right")

    def _save(self):
        for deck_id, var in self._vars.items():
            if var.get():
                self._deck_service.add_card(deck_id, self.card["id"])
            else:
                self._deck_service.remove_card(deck_id, self.card["id"])
        if self.on_done:
            self.on_done()
        self.destroy()
