"""
ui/virtual_keyboard.py — On-screen hiragana/katakana keyboard.

A floating, always-on-top panel. Clicking a key inserts that character
into whichever text entry last had keyboard focus — this works across
the main window AND any child dialog (CardForm, TypingView, the table
search box, etc.) because Tk tracks focus application-wide, not per
window: we bind_all("<FocusIn>") once and remember the last widget that
looks like a text entry, so the keyboard doesn't need to know which
window or field the user was typing into.

The character grid below is a *display/layout* concern (which row/column
each kana sits in on a gojuon table) — deliberately kept separate from
domain/kana.py, whose job is romaji<->kana conversion, not keyboard
layout. Different reason to exist, so a different table, even though the
characters overlap.
"""
import customtkinter as ctk
import tkinter as tk

from constants import KB_TOGGLE_KEYBOARD

# ── Gojuon grid layout: each cell is (hiragana, katakana) or None for a gap ──
_BASE_ROWS = [
    [("あ", "ア"), ("い", "イ"), ("う", "ウ"), ("え", "エ"), ("お", "オ")],
    [("か", "カ"), ("き", "キ"), ("く", "ク"), ("け", "ケ"), ("こ", "コ")],
    [("さ", "サ"), ("し", "シ"), ("す", "ス"), ("せ", "セ"), ("そ", "ソ")],
    [("た", "タ"), ("ち", "チ"), ("つ", "ツ"), ("て", "テ"), ("と", "ト")],
    [("な", "ナ"), ("に", "ニ"), ("ぬ", "ヌ"), ("ね", "ネ"), ("の", "ノ")],
    [("は", "ハ"), ("ひ", "ヒ"), ("ふ", "フ"), ("へ", "ヘ"), ("ほ", "ホ")],
    [("ま", "マ"), ("み", "ミ"), ("む", "ム"), ("め", "メ"), ("も", "モ")],
    [("や", "ヤ"), None, ("ゆ", "ユ"), None, ("よ", "ヨ")],
    [("ら", "ラ"), ("り", "リ"), ("る", "ル"), ("れ", "レ"), ("ろ", "ロ")],
    [("わ", "ワ"), None, None, None, ("を", "ヲ")],
    [("ん", "ン"), ("っ", "ッ"), ("ー", "ー"), None, None],
]

_DAKUTEN_ROWS = [
    [("が", "ガ"), ("ぎ", "ギ"), ("ぐ", "グ"), ("げ", "ゲ"), ("ご", "ゴ")],
    [("ざ", "ザ"), ("じ", "ジ"), ("ず", "ズ"), ("ぜ", "ゼ"), ("ぞ", "ゾ")],
    [("だ", "ダ"), ("ぢ", "ヂ"), ("づ", "ヅ"), ("で", "デ"), ("ど", "ド")],
    [("ば", "バ"), ("び", "ビ"), ("ぶ", "ブ"), ("べ", "ベ"), ("ぼ", "ボ")],
    [("ぱ", "パ"), ("ぴ", "ピ"), ("ぷ", "プ"), ("ぺ", "ペ"), ("ぽ", "ポ")],
]

_YOUON_ROWS = [
    [("きゃ", "キャ"), ("きゅ", "キュ"), ("きょ", "キョ")],
    [("しゃ", "シャ"), ("しゅ", "シュ"), ("しょ", "ショ")],
    [("ちゃ", "チャ"), ("ちゅ", "チュ"), ("ちょ", "チョ")],
    [("にゃ", "ニャ"), ("にゅ", "ニュ"), ("にょ", "ニョ")],
    [("ひゃ", "ヒャ"), ("ひゅ", "ヒュ"), ("ひょ", "ヒョ")],
    [("みゃ", "ミャ"), ("みゅ", "ミュ"), ("みょ", "ミョ")],
    [("りゃ", "リャ"), ("りゅ", "リュ"), ("りょ", "リョ")],
    [("ぎゃ", "ギャ"), ("ぎゅ", "ギュ"), ("ぎょ", "ギョ")],
    [("じゃ", "ジャ"), ("じゅ", "ジュ"), ("じょ", "ジョ")],
    [("びゃ", "ビャ"), ("びゅ", "ビュ"), ("びょ", "ビョ")],
    [("ぴゃ", "ピャ"), ("ぴゅ", "ピュ"), ("ぴょ", "ピョ")],
]

_SECTIONS = {
    "五十音": _BASE_ROWS,
    "濁音":   _DAKUTEN_ROWS,
    "拗音":   _YOUON_ROWS,
}

# Widgets we're willing to type into. Anything else that receives focus
# (buttons, the keyboard's own controls, etc.) is ignored so it never
# overwrites the remembered target.
_TEXT_WIDGET_TYPES = (ctk.CTkEntry, ctk.CTkTextbox, tk.Entry, tk.Text)


class VirtualKeyboard(ctk.CTkToplevel):
    """
    Floating hiragana/katakana keyboard. Create once and keep it around —
    toggle visibility with show()/hide()/toggle() rather than destroying
    it, so its position and hiragana/katakana mode survive being hidden.
    """

    def __init__(self, master):
        super().__init__(master)
        self.title("⌨️  Bàn phím ảo")
        self.geometry("330x430")
        self.minsize(300, 380)
        self.resizable(True, True)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.hide)

        self._target = None         # last-focused text widget, or None
        self._mode = "hiragana"     # or "katakana"
        self._section = "五十音"

        # Track focus application-wide (works across every window/dialog
        # in the app, not just this one — see module docstring).
        self.bind_all("<FocusIn>", self._on_focus_in, add="+")

        self._build()
        self._render_grid()

        # Start hidden — App decides when to show it (toggle button/shortcut).
        self.withdraw()

    # ── Visibility ───────────────────────────────────────────────────────────

    def show(self):
        self.deiconify()
        self.lift()

    def hide(self):
        self.withdraw()

    def toggle(self):
        if self.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    # ── Focus tracking ───────────────────────────────────────────────────────

    def _on_focus_in(self, event):
        w = event.widget
        if isinstance(w, _TEXT_WIDGET_TYPES):
            self._target = w

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Hiragana / Katakana switch
        self._mode_switch = ctk.CTkSegmentedButton(
            self, values=["ひらがな", "カタカナ"],
            command=self._on_mode_change)
        self._mode_switch.set("ひらがな")
        self._mode_switch.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")

        # Section tabs (base / dakuten / youon)
        self._section_switch = ctk.CTkSegmentedButton(
            self, values=list(_SECTIONS.keys()),
            command=self._on_section_change)
        self._section_switch.set(self._section)
        self._section_switch.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")

        # Key grid
        self._grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._grid_frame.grid(row=2, column=0, padx=10, pady=0, sticky="nsew")

        # Bottom controls: space / backspace / clear
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        ctrl.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(ctrl, text="␣ Cách", command=self._insert_space
                      ).grid(row=0, column=0, padx=3, sticky="ew")
        ctk.CTkButton(ctrl, text="⌫ Xóa", command=self._backspace
                      ).grid(row=0, column=1, padx=3, sticky="ew")
        ctk.CTkButton(ctrl, text="🗑️ Xóa hết", fg_color=("gray70", "gray30"),
                      command=self._clear
                      ).grid(row=0, column=2, padx=3, sticky="ew")

    def _on_mode_change(self, value):
        self._mode = "hiragana" if value == "ひらがな" else "katakana"
        self._render_grid()

    def _on_section_change(self, value):
        self._section = value
        self._render_grid()

    def _render_grid(self):
        for w in self._grid_frame.winfo_children():
            w.destroy()

        rows = _SECTIONS[self._section]
        idx = 0 if self._mode == "hiragana" else 1
        n_cols = max(len(r) for r in rows)
        for c in range(n_cols):
            self._grid_frame.grid_columnconfigure(c, weight=1)

        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                char = cell[idx]
                btn = ctk.CTkButton(
                    self._grid_frame, text=char, width=48, height=34,
                    font=ctk.CTkFont(size=15),
                    command=lambda ch=char: self._insert(ch))
                btn.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")

    # ── Insert / edit actions on the remembered target widget ──────────────────

    def _insert(self, char):
        w = self._target
        if w is None:
            return
        try:
            w.insert(tk.INSERT, char)
            w.focus_set()
        except Exception:
            pass

    def _insert_space(self):
        self._insert(" ")

    def _backspace(self):
        w = self._target
        if w is None:
            return
        try:
            if isinstance(w, (ctk.CTkTextbox, tk.Text)):
                w.delete("insert-1c", "insert")
            else:
                pos = w.index(tk.INSERT)
                if pos > 0:
                    w.delete(pos - 1, pos)
            w.focus_set()
        except Exception:
            pass

    def _clear(self):
        w = self._target
        if w is None:
            return
        try:
            if isinstance(w, (ctk.CTkTextbox, tk.Text)):
                w.delete("1.0", "end")
            else:
                w.delete(0, tk.END)
            w.focus_set()
        except Exception:
            pass
