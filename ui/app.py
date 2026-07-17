import customtkinter as ctk
import re
import logging
from ui.sidebar import Sidebar
from ui.review_today import ReviewTodayDialog
from ui.tooltip import Tooltip
from ui.table_view import TableView
from ui.stats_view import StatsView
from ui.flashcard import FlashcardLauncher
from ui.quiz import QuizLauncher
from ui.backup_view import BackupView
from ui.typing_practice import TypingLauncher
from ui.sync_dialog import SyncDialog
from ui.virtual_keyboard import VirtualKeyboard
from infrastructure import settings
from application.stats_service import StatsService
from application.card_service import CardService
from application.deck_service import DeckService
from application.study_service import StudyService
from infrastructure.db.sqlite_repositories import (
    SqliteStatsRepository, SqliteCardRepository, SqliteDeckRepository,
    SqliteStudySessionRepository,
)
from constants import (
    KB_NEW_CARD, KB_FOCUS_SEARCH, KB_REFRESH, KB_ESCAPE, KB_TOGGLE_KEYBOARD,
    SETTING_LAST_TAB, SETTING_THEME,
)

logger = logging.getLogger(__name__)


class App(ctk.CTk):
    def __init__(self, stats_service=None, card_service=None, deck_service=None, study_service=None):
        super().__init__()

        # ── Composition root (Stage 4 of the clean-architecture migration) ──
        # main.pyw is expected to build and pass all four services in; the
        # defaults here only exist so App() still works standalone (e.g.
        # if something constructs it without wiring anything explicitly).
        self.stats_service = stats_service if stats_service is not None else StatsService(SqliteStatsRepository())
        self.card_service  = card_service  if card_service  is not None else CardService(SqliteCardRepository())
        self.deck_service  = deck_service  if deck_service  is not None else DeckService(SqliteDeckRepository())
        self.study_service = study_service if study_service is not None else StudyService(SqliteStudySessionRepository())

        self._vk = None   # VirtualKeyboard, created lazily on first toggle

        # ── Restore theme before building UI ──────────────────────────────────
        theme = settings.get("theme", "dark")
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")

        self.title("🇯🇵  Học Tiếng Nhật — Kho từ vựng")
        self._restore_geometry()
        self.minsize(960, 620)

        self._build()

        # ── Restore last tab ──────────────────────────────────────────────────
        last_tab = settings.get("last_tab", "table")
        if last_tab == "stats":
            self.after(100, lambda: self._switch_tab("stats"))

        # ── Save state on close ───────────────────────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _restore_geometry(self):
        geo = settings.get("window_geo", "1280x760")
        x   = settings.get("window_x")
        y   = settings.get("window_y")

        m = re.match(r"^(\d+)x(\d+)$", geo)
        w, h = (int(m.group(1)), int(m.group(2))) if m else (1280, 760)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # Chừa khoảng an toàn cho taskbar/title bar hệ điều hành
        margin = 60

        # Kẹp chiều rộng/cao lại vừa màn hình hiện tại (không vượt quá dù đã lưu
        # geometry từ một màn hình khác lớn hơn trước đó)
        w = max(960, min(w, sw))
        h = max(620, min(h, sh - margin))

        if x is None or y is None:
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)

        # Kẹp vị trí để toàn bộ cửa sổ (kể cả cạnh dưới/phải) luôn nằm trong màn hình
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h - margin))

        self.geometry(f"{w}x{h}+{x}+{y}")

    def _on_close(self):
        """Save window state then quit."""
        try:
            self.update_idletasks()
            geo = self.wm_geometry()   # e.g. "1280x760+100+50" or "1280x760-50+30"
            m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", geo)
            if m:
                w, h, x, y = m.groups()
                settings.update({
                    "window_geo":   f"{w}x{h}",
                    "window_x":     int(x),
                    "window_y":     int(y),
                    "last_tab":     self._current_tab,
                    "theme":        ctk.get_appearance_mode().lower(),
                })
            else:
                logger.warning(f"Could not parse window geometry: {geo!r}")
                settings.update({
                    "last_tab": self._current_tab,
                    "theme":    ctk.get_appearance_mode().lower(),
                })
        except Exception as e:
            logger.warning(f"Failed to save window state on close: {e}")
        self.destroy()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Top nav bar ──
        navbar = ctk.CTkFrame(self, corner_radius=0, height=46,
                               fg_color=("gray88", "gray15"))
        navbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        navbar.grid_propagate(False)
        # Cột 9 = spacer đẩy theme btn về bên phải
        navbar.grid_columnconfigure(9, weight=1)

        ctk.CTkLabel(navbar, text="🇯🇵  日本語",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     anchor="w").grid(row=0, column=0, padx=(16, 24), pady=10)

        tab_cfg  = dict(width=120, height=32, corner_radius=6)
        inactive = dict(fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"))

        self._tab_table = ctk.CTkButton(
            navbar, text="🗂️  Thư viện", **tab_cfg,
            command=lambda: self._switch_tab("table"))
        self._tab_table.grid(row=0, column=1, padx=4, pady=7)

        self._tab_stats = ctk.CTkButton(
            navbar, text="📊  Thống kê", **tab_cfg, **inactive,
            command=lambda: self._switch_tab("stats"))
        self._tab_stats.grid(row=0, column=2, padx=4, pady=7)

        review_btn = ctk.CTkButton(
            navbar, text="🎯  Ôn tập hôm nay", **tab_cfg,
            fg_color="#E8A33D", hover_color="#C9862A", text_color="white",
            command=self._open_review_today
        )
        review_btn.grid(row=0, column=3, padx=4, pady=7)
        Tooltip(review_btn,
                "Ôn đúng những thẻ cần ôn lại hôm nay, dựa trên mức độ "
                "bạn đã nhớ chúng (lặp lại ngắt quãng - SRS).\n"
                "Thẻ dễ sẽ giãn cách ôn xa hơn, thẻ khó quay lại sớm hơn.")

        ctk.CTkButton(
            navbar, text="🃏  Flashcard", **tab_cfg, **inactive,
            command=self._open_flashcard
        ).grid(row=0, column=4, padx=4, pady=7)

        ctk.CTkButton(
            navbar, text="📝  Quiz", **tab_cfg, **inactive,
            command=self._open_quiz
        ).grid(row=0, column=5, padx=4, pady=7)

        ctk.CTkButton(
            navbar, text="⌨️  Gõ", **tab_cfg, **inactive,
            command=self._open_typing
        ).grid(row=0, column=6, padx=4, pady=7)

        self._vk_toggle_btn = ctk.CTkButton(
            navbar, text="🈴  Bàn phím ảo", **tab_cfg, **inactive,
            command=self._toggle_keyboard
        )
        self._vk_toggle_btn.grid(row=0, column=7, padx=4, pady=7)
        Tooltip(self._vk_toggle_btn,
                "Bật/tắt bàn phím ảo hiragana/katakana (F8).\n"
                "Nhấn phím trên bàn phím ảo sẽ gõ vào ô nhập liệu "
                "bạn vừa chọn — kể cả trong hộp thoại đang mở.")

        ctk.CTkButton(
            navbar, text="💾  Backup", **tab_cfg, **inactive,
            command=self._open_backup
        ).grid(row=0, column=8, padx=4, pady=7)

        # ── Nút Sync mới ──────────────────────────────────────────────────────
        self._sync_btn = ctk.CTkButton(
            navbar, text="☁️  Sync", **tab_cfg, **inactive,
            command=self._open_sync
        )
        self._sync_btn.grid(row=0, column=9, padx=4, pady=7)

        # Theme toggle (bên phải cùng)
        ctk.CTkButton(
            navbar,
            text="☀️" if ctk.get_appearance_mode() == "Dark" else "🌙",
            width=34, height=34, corner_radius=17,
            fg_color="transparent", hover_color=("gray75", "gray35"),
            font=ctk.CTkFont(size=16), command=self._toggle_theme
        ).grid(row=0, column=10, padx=(0, 12), pady=6)

        # ── Sidebar ──
        self.sidebar = Sidebar(self, self.card_service, self.deck_service, self.stats_service,
                                on_select_callback=self._on_filter_change)
        self.sidebar.grid(row=1, column=0, sticky="nsew")

        # ── Main content ──
        self.table = TableView(self, card_service=self.card_service, deck_service=self.deck_service)
        self.table.grid(row=1, column=1, sticky="nsew")

        self.stats = StatsView(self, stats_service=self.stats_service)
        self.stats.grid(row=1, column=1, sticky="nsew")
        self.stats.grid_remove()

        self.sidebar.activate_default()
        self._current_tab = "table"
        self._bind_shortcuts()

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self, tab: str):
        if tab == self._current_tab:
            return
        self._current_tab = tab
        active   = {}
        inactive = dict(fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"))

        if tab == "table":
            self.stats.grid_remove()
            self.table.grid()
            self.sidebar.grid()
            self._tab_table.configure(**active)
            self._tab_stats.configure(**inactive)
        elif tab == "stats":
            self.table.grid_remove()
            self.sidebar.grid_remove()
            self.stats.grid()
            self.stats.refresh()
            self._tab_table.configure(**inactive)
            self._tab_stats.configure(**active)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _bind_shortcuts(self):
        """Global keyboard shortcuts."""
        self.bind(KB_NEW_CARD, lambda _: (
            self._switch_tab("table") or self.table._add_card()))
        self.bind(KB_FOCUS_SEARCH, lambda _: (
            self._switch_tab("table") or self.table._focus_search()))
        self.bind(KB_REFRESH, lambda _: (
            self.table.load_cards() if self._current_tab == "table"
            else self.stats.refresh(force=True)))
        # bind_all (not bind): the keyboard is most useful while typing in a
        # child dialog (CardForm, TypingView...), which self.bind wouldn't reach.
        self.bind_all(KB_TOGGLE_KEYBOARD, lambda _: self._toggle_keyboard())

    def _open_review_today(self):
        ReviewTodayDialog(self, self.card_service, self.deck_service, self.study_service)

    def _open_flashcard(self):
        FlashcardLauncher(self, self.card_service, self.deck_service, self.study_service)

    def _open_quiz(self):
        QuizLauncher(self, self.card_service, self.deck_service, self.study_service)

    def _open_typing(self):
        TypingLauncher(self, self.card_service, self.deck_service, self.study_service)

    def _toggle_keyboard(self):
        if self._vk is None:
            self._vk = VirtualKeyboard(self)
        self._vk.toggle()

    def _open_backup(self):
        BackupView(self)

    def _open_sync(self):
        """Mở dialog sync Google Drive."""
        def on_done():
            # Reload table + stats sau khi sync xong
            if hasattr(self, "table"):
                self.table.load_cards()
            if hasattr(self, "sidebar"):
                self.sidebar.refresh_stats()
                self.sidebar.refresh_decks()
            if hasattr(self, "stats") and self._current_tab == "stats":
                self.stats.refresh(force=True)

        SyncDialog(self, on_sync_done=on_done)

    def _on_filter_change(self, filter_val):
        if hasattr(self, "table"):
            self.table.set_filter(filter_val)

    def _toggle_theme(self):
        new  = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(new)
        settings.set("theme", new)
        if hasattr(self, "table"):
            self.table.refresh_theme()
        if hasattr(self, "stats") and self._current_tab == "stats":
            self.stats.refresh()
