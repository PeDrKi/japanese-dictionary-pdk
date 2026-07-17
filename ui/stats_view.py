import customtkinter as ctk
import threading
import logging
import tkinter as tk
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


# ── Colour palette ─────────────────────────────────────────────────────────────
PALETTE = ["#4A90D9","#4ECB85","#F0B429","#E85D5D","#9B7FE8","#3ECFCF","#F97316","#FF6B9D"]
TYPE_COLOR   = {"kanji":"#F0B429","hiragana":"#3ECFCF","katakana":"#9B7FE8","vocab":"#4ECB85"}
STATUS_COLOR = {"new":"#6B8CFF","learning":"#F0B429","known":"#4ECB85"}


class StatsView(ctk.CTkFrame):
    def __init__(self, master, stats_service, **kwargs):
        super().__init__(master, corner_radius=0, **kwargs)
        self._stats_service = stats_service
        self._build()
        self.refresh()

    # ── Skeleton ──────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top bar
        topbar = ctk.CTkFrame(self, fg_color=("gray92","gray18"),
                              corner_radius=0, height=52)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)

        ctk.CTkLabel(topbar, text="📊  Thống kê",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     anchor="w").pack(side="left", padx=16, pady=12)

        ctk.CTkButton(topbar, text="🔄  Làm mới", width=110, height=34,
                      corner_radius=6,
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self.refresh).pack(side="right", padx=14, pady=9)

        # Scrollable body
        self._scroll = ctk.CTkScrollableFrame(self, corner_radius=0,
                                               fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew")

    # ── Refresh ───────────────────────────────────────────────────────────────

    _cached_stats = None
    _stats_ts     = 0

    def refresh(self, force=False):
        import time
        now = time.time()
        # Use cache if fresh enough
        if not force and self._cached_stats and (now - self._stats_ts) < 30:
            self._render_cached()
            return
        # Show loading indicator immediately
        self._show_loading()
        # Fetch data in background thread — never block UI
        def _fetch():
            try:
                s = self._stats_service.get_full()
                StatsView._cached_stats = s
                StatsView._stats_ts     = time.time()
            except Exception as e:
                logger.warning(f"Failed to load stats, falling back to cache: {e}")
                s = self._cached_stats or {}
            # Update UI from main thread
            if self.winfo_exists():
                self.after(0, lambda: self._render_data(s))
        threading.Thread(target=_fetch, daemon=True).start()

    def _show_loading(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._scroll, text="⏳  Đang tải...",
                     font=ctk.CTkFont(size=13),
                     text_color=("gray55","gray50")).pack(pady=40)

    def _render_cached(self):
        if self._cached_stats:
            for w in self._scroll.winfo_children():
                w.destroy()
            self._render(self._cached_stats)

    def _render_data(self, s: dict):
        if not self.winfo_exists():
            return
        for w in self._scroll.winfo_children():
            w.destroy()
        if s:
            self._render(s)

    # ── Render all sections ───────────────────────────────────────────────────

    def _render(self, s):
        f = self._scroll

        # ── Row 1: KPI cards ──
        kpi_row = ctk.CTkFrame(f, fg_color="transparent")
        kpi_row.pack(fill="x", padx=20, pady=(20, 8))

        total    = s["total"]
        known    = s["by_status"].get("known", 0)
        learning = s["by_status"].get("learning", 0)
        new_c    = s["by_status"].get("new", 0)
        pct      = round(known / total * 100) if total else 0
        sessions = s["total_sessions"]
        acc      = round(s["correct_sessions"] / sessions * 100) if sessions else 0

        kpis = [
            ("📚", str(total),    "Tổng thẻ",       "#4A90D9"),
            ("✅", str(known),    "Đã nhớ",          "#4ECB85"),
            ("📖", str(learning), "Đang học",        "#F0B429"),
            ("🆕", str(new_c),    "Chưa học",        "#6B8CFF"),
            ("🎯", f"{pct}%",     "Tỉ lệ nhớ",       "#9B7FE8"),
            ("⭐", str(s["favorites"]), "Yêu thích",  "#F0B429"),
            ("🔁", str(sessions), "Lần ôn",          "#3ECFCF"),
            ("💯", f"{acc}%",     "Độ chính xác",    "#4ECB85"),
        ]
        for i, (icon, num, lbl, color) in enumerate(kpis):
            card = ctk.CTkFrame(kpi_row, fg_color=("gray88","gray20"),
                                corner_radius=10)
            card.grid(row=0, column=i, padx=5, sticky="ew")
            kpi_row.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=20)
                         ).pack(pady=(12,2))
            ctk.CTkLabel(card, text=num,
                         font=ctk.CTkFont(size=22, weight="bold"),
                         text_color=color).pack()
            ctk.CTkLabel(card, text=lbl,
                         font=ctk.CTkFont(size=10),
                         text_color=("gray55","gray55")).pack(pady=(0,10))

        # ── Row 2: Status donut + Type bar ──
        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=8)
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=2)

        self._donut_card(row2, "Trạng thái học", s["by_status"], STATUS_COLOR
                         ).grid(row=0, column=0, padx=(0,8), sticky="nsew")
        self._hbar_card(row2, "Loại ký tự", s["by_type"], TYPE_COLOR
                        ).grid(row=0, column=1, sticky="nsew")

        # ── Row 3: JLPT bar + Deck sizes ──
        row3 = ctk.CTkFrame(f, fg_color="transparent")
        row3.pack(fill="x", padx=20, pady=8)
        row3.grid_columnconfigure(0, weight=1)
        row3.grid_columnconfigure(1, weight=1)

        jlpt_colors = {"N5":"#4ECB85","N4":"#3ECFCF","N3":"#4A90D9",
                       "N2":"#9B7FE8","N1":"#E85D5D","なし":"#6B7280"}
        self._hbar_card(row3, "Phân bổ JLPT", s["by_jlpt"], jlpt_colors
                        ).grid(row=0, column=0, padx=(0,8), sticky="nsew")
        self._hbar_card(row3, "Số thẻ theo Bộ thẻ",
                        dict(s["deck_sizes"]), {}
                        ).grid(row=0, column=1, sticky="nsew")

        # ── Row 4: Daily added chart ──
        if s["daily_added"]:
            self._line_card(f, "📅  Thẻ mới thêm (30 ngày qua)",
                            s["daily_added"], "#4A90D9")
        else:
            self._empty_card(f, "📅  Thẻ mới thêm (30 ngày qua)",
                             "Chưa có dữ liệu trong 30 ngày qua")

        # ── Row 5: Daily study chart ──
        if s["daily_study"]:
            self._line_card(f, "🔁  Lần ôn mỗi ngày (30 ngày qua)",
                            s["daily_study"], "#4ECB85")
        else:
            self._empty_card(f, "🔁  Lần ôn mỗi ngày (30 ngày qua)",
                             "Chưa có phiên ôn tập nào")

        # ── Row 6: Field completeness ──
        self._completeness_card(f, s["completeness"])

        # Bottom padding
        ctk.CTkFrame(f, height=32, fg_color="transparent").pack()

    # ── Chart widgets ─────────────────────────────────────────────────────────

    def _card_frame(self, parent, title):
        outer = ctk.CTkFrame(parent, fg_color=("gray88","gray20"), corner_radius=10)
        ctk.CTkLabel(outer, text=title,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").pack(fill="x", padx=14, pady=(12,6))
        ctk.CTkFrame(outer, height=1,
                     fg_color=("gray80","gray30")).pack(fill="x", padx=14, pady=(0,8))
        return outer

    def _dark(self):
        return ctk.get_appearance_mode() == "Dark"

    # Donut chart
    def _donut_card(self, parent, title, data: dict, color_map: dict):
        frame = self._card_frame(parent, title)
        if not data or sum(data.values()) == 0:
            ctk.CTkLabel(frame, text="Không có dữ liệu",
                         text_color=("gray55","gray55")).pack(pady=20)
            return frame

        total = sum(data.values())
        size  = 160
        cv_bg = "#1e2130" if self._dark() else "#f0f0f0"

        canvas = tk.Canvas(frame, width=size, height=size,
                           bg=cv_bg, highlightthickness=0)
        canvas.pack(pady=4)

        start = -90.0
        pad   = 8
        for key, val in data.items():
            extent = 360 * val / total
            color  = color_map.get(key, PALETTE[0])
            canvas.create_arc(pad, pad, size-pad, size-pad,
                               start=start, extent=extent,
                               fill=color, outline=cv_bg, width=2)
            start += extent

        # Center hole
        hole = 44
        canvas.create_oval(size//2-hole, size//2-hole,
                            size//2+hole, size//2+hole,
                            fill=cv_bg, outline=cv_bg)
        fg = "#e8eaf0" if self._dark() else "#1a1a2e"
        canvas.create_text(size//2, size//2, text=str(total),
                            font=("Segoe UI", 16, "bold"), fill=fg)

        # Legend
        leg = ctk.CTkFrame(frame, fg_color="transparent")
        leg.pack(fill="x", padx=14, pady=(0,12))
        for key, val in data.items():
            color = color_map.get(key, PALETTE[0])
            row   = ctk.CTkFrame(leg, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text="■", text_color=color,
                         font=ctk.CTkFont(size=12), width=18).pack(side="left")
            ctk.CTkLabel(row, text=f"{key}",
                         font=ctk.CTkFont(size=11), anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=f"{val}  ({round(val/total*100)}%)",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50","gray55")).pack(side="right")
        return frame

    # Horizontal bar chart
    def _hbar_card(self, parent, title, data: dict, color_map: dict):
        frame = self._card_frame(parent, title)
        if not data or sum(data.values()) == 0:
            ctk.CTkLabel(frame, text="Không có dữ liệu",
                         text_color=("gray55","gray55")).pack(pady=20)
            return frame

        total   = sum(data.values())
        max_val = max(data.values())
        inner   = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(0,12))

        for i, (key, val) in enumerate(sorted(data.items(),
                                               key=lambda x: x[1], reverse=True)):
            color = color_map.get(key, PALETTE[i % len(PALETTE)])
            row   = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=str(key), width=70,
                         font=ctk.CTkFont(size=11), anchor="w"
                         ).grid(row=0, column=0, sticky="w")

            bar_outer = ctk.CTkFrame(row, fg_color=("gray80","gray30"),
                                     corner_radius=4, height=18)
            bar_outer.grid(row=0, column=1, sticky="ew", padx=(4,8))
            bar_outer.grid_propagate(False)
            bar_outer.grid_columnconfigure(0, weight=1)

            pct_w = max(0.04, val / max_val)
            bar_inner = ctk.CTkFrame(bar_outer, fg_color=color,
                                      corner_radius=4, height=18)
            bar_inner.place(relx=0, rely=0, relwidth=pct_w, relheight=1.0)

            ctk.CTkLabel(row, text=f"{val}",
                         font=ctk.CTkFont(size=11),
                         text_color=("gray50","gray55"), width=30
                         ).grid(row=0, column=2, sticky="e")
        return frame

    # Line / bar chart for time series
    def _line_card(self, parent, title, data, color):
        frame = self._card_frame(parent, title)
        frame.pack(fill="x", padx=0, pady=8)

        W, H  = 700, 140
        pad_l, pad_r, pad_t, pad_b = 40, 20, 16, 30
        cv_bg = "#1e2130" if self._dark() else "#f0f0f0"
        fg    = "#6b7280"

        canvas = tk.Canvas(frame, width=W, height=H, bg=cv_bg,
                           highlightthickness=0)
        canvas.pack(padx=14, pady=(0,12), fill="x")

        if not data:
            canvas.create_text(W//2, H//2, text="Không có dữ liệu",
                                fill=fg, font=("Segoe UI", 11))
            return frame

        vals  = [v for _, v in data]
        dates = [d for d, _ in data]
        max_v = max(vals) or 1

        cw = W - pad_l - pad_r
        ch = H - pad_t - pad_b
        bar_w = max(4, cw // len(vals) - 2)

        # Grid lines
        for i in range(5):
            y = pad_t + ch * i // 4
            canvas.create_line(pad_l, y, W-pad_r, y,
                                fill=fg, dash=(2,4), width=1)
            lbl = str(round(max_v * (4-i) / 4))
            canvas.create_text(pad_l-4, y, text=lbl, anchor="e",
                                fill=fg, font=("Segoe UI", 8))

        # Bars
        for i, (date, val) in enumerate(data):
            x = pad_l + i * (cw / len(data)) + (cw / len(data) - bar_w) / 2
            bar_h = ch * val / max_v
            y0 = pad_t + ch - bar_h
            y1 = pad_t + ch
            canvas.create_rectangle(x, y0, x+bar_w, y1,
                                     fill=color, outline="", width=0)

        # X-axis labels (show first, middle, last)
        show_idx = {0, len(dates)//2, len(dates)-1}
        for i, date in enumerate(dates):
            if i in show_idx:
                x = pad_l + i * (cw / len(data)) + (cw / len(data)) / 2
                lbl = date[-5:] if date else ""   # MM-DD
                canvas.create_text(x, H-pad_b+12, text=lbl, fill=fg,
                                    font=("Segoe UI", 8))
        return frame

    # Completeness bars
    def _completeness_card(self, parent, comp: dict):
        frame = self._card_frame(parent, "📋  Độ đầy đủ dữ liệu các trường")
        frame.pack(fill="x", padx=0, pady=8)

        LABELS = {
            "reading_on":   "On-yomi",    "reading_kun":  "Kun-yomi",
            "reading_kana": "Kana",       "romaji":       "Romaji",
            "meaning_vi":   "Nghĩa VN",   "meaning_en":   "Nghĩa EN",
            "example_jp":   "Ví dụ JP",   "example_vi":   "Ví dụ VI",
            "stroke_count": "Số nét",     "jlpt_level":   "JLPT",
            "source":       "Nguồn",      "notes":        "Ghi chú",
        }

        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0,12))

        items = list(comp.items())
        cols  = 3
        for i, (field, pct) in enumerate(items):
            r, c = divmod(i, cols)
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=r, column=c, padx=8, pady=4, sticky="ew")
            grid.grid_columnconfigure(c, weight=1)

            ctk.CTkLabel(cell, text=LABELS.get(field, field),
                         font=ctk.CTkFont(size=11), anchor="w").pack(fill="x")

            bar_bg = ctk.CTkFrame(cell, fg_color=("gray80","gray30"),
                                   corner_radius=4, height=10)
            bar_bg.pack(fill="x", pady=(2,0))
            bar_bg.pack_propagate(False)

            bar_color = "#4ECB85" if pct >= 80 else "#F0B429" if pct >= 40 else "#E85D5D"
            bar_fill  = ctk.CTkFrame(bar_bg, fg_color=bar_color,
                                      corner_radius=4, height=10)
            bar_fill.place(relx=0, rely=0, relwidth=max(0.02, pct/100), relheight=1.0)

            ctk.CTkLabel(cell, text=f"{pct}%",
                         font=ctk.CTkFont(size=10),
                         text_color=("gray50","gray55")).pack(anchor="e")

    def _empty_card(self, parent, title, msg):
        frame = self._card_frame(parent, title)
        frame.pack(fill="x", padx=0, pady=8)
        ctk.CTkLabel(frame, text=msg,
                     font=ctk.CTkFont(size=12),
                     text_color=("gray55","gray50")).pack(pady=20)
