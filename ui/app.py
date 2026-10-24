import customtkinter as ctk
import re
import logging
from ui.sidebar import Sidebar
from ui.review_today import ReviewTodayDialog
from ui.tooltip import Tooltip
from ui.table_view import TableView
from ui.stats_view import StatsView
from ui.radical_view import RadicalView
from ui.grammar_view import GrammarView
from ui.conj_view import ConjView
from ui.translation_view import TranslationsView
from application.material_service import MaterialService
from ui.flashcard import FlashcardLauncher
from ui.quiz import QuizLauncher
from ui.backup_view import BackupView
from ui.typing_practice import TypingLauncher
from ui.sync_dialog import SyncDialog, get_saved_config as get_sync_config
from ui.sync_toast import SyncToast
from ui.threadsafe import call_in_ui, install as install_threadsafe
from infrastructure.cloud_config import make_syncer
import threading
from ui.virtual_keyboard import VirtualKeyboard
from ui.shortcuts_dialog import ShortcutsDialog
from infrastructure import settings
from application.stats_service import StatsService
from application.card_service import CardService
from application.deck_service import DeckService
from application.study_service import StudyService
from application.decomposition_service import DecompositionService
from application.radical_service import RadicalService
from infrastructure.db.sqlite_repositories import (
    SqliteStatsRepository, SqliteCardRepository, SqliteDeckRepository,
    SqliteStudySessionRepository, SqliteRadicalRepository, SqliteUserDecompositionRepository,
    SqliteMaterialRepository,
)
from infrastructure.kanji_ids import FileKanjiIdsRepository
from constants import (
    KB_NEW_CARD, KB_FOCUS_SEARCH, KB_REFRESH, KB_ESCAPE, KB_TOGGLE_KEYBOARD,
    KB_TAB_TABLE, KB_TAB_STATS, KB_TAB_RADICALS, KB_TAB_GRAMMAR, KB_TAB_CONJ, KB_TAB_TRANS, KB_REVIEW_TODAY, KB_FLASHCARD, KB_QUIZ,
    KB_TYPING, KB_BACKUP, KB_SYNC, KB_HELP,
    SETTING_LAST_TAB, SETTING_THEME,
)

logger = logging.getLogger(__name__)


class App(ctk.CTk):
    def __init__(self, stats_service=None, card_service=None, deck_service=None, study_service=None,
                 decomposition_service=None, radical_service=None, material_service=None):
        super().__init__()

        # ── Composition root (Stage 4 of the clean-architecture migration) ──
        # main.pyw is expected to build and pass all four services in; the
        # defaults here only exist so App() still works standalone (e.g.
        # if something constructs it without wiring anything explicitly).
        self.stats_service = stats_service if stats_service is not None else StatsService(SqliteStatsRepository())
        self.card_service  = card_service  if card_service  is not None else CardService(SqliteCardRepository())
        self.deck_service  = deck_service  if deck_service  is not None else DeckService(SqliteDeckRepository())
        self.study_service = study_service if study_service is not None else StudyService(SqliteStudySessionRepository())
        # File-backed, not SQLite — no DB needed for an offline dataset lookup.
        # user_overrides (SQLite) lets the person override/replace that
        # bundled data per-character — see ui/kanji_decomposition_dialog.py's
        # "✏️ Sửa" button.
        self.decomposition_service = (decomposition_service if decomposition_service is not None
                                       else DecompositionService(FileKanjiIdsRepository(),
                                                                  SqliteUserDecompositionRepository()))
        self.radical_service = radical_service if radical_service is not None else RadicalService(SqliteRadicalRepository())

        self.material_service = material_service if material_service is not None else MaterialService(
            SqliteMaterialRepository(), self.card_service, self.deck_service)

        install_threadsafe(self)   # luồng nền (sync, Jisho, dịch, thống kê) đẩy việc về luồng giao diện qua hàng đợi
        self._vk = None   # VirtualKeyboard, created lazily on first toggle
        self._sync_in_progress = False  # chặn auto-sync và sync tay đè lên nhau

        # ── Restore theme before building UI ──────────────────────────────────
        theme = settings.get("theme", "dark")
        ctk.set_appearance_mode(theme)
        ctk.set_default_color_theme("blue")

        self.title("🇯🇵  Học Tiếng Nhật — Kho từ vựng")
        self._restore_geometry()
        self.minsize(1040, 620)

        self._build()

        # ── Restore last tab ──────────────────────────────────────────────────
        last_tab = settings.get("last_tab", "table")
        if last_tab == "stats":
            self.after(100, lambda: self._switch_tab("stats"))

        # ── Tự động sync ngầm khi mở app (im lặng nếu chưa cấu hình Supabase,
        # hoặc nếu không có gì thay đổi) ────────────────────────────────────
        self.after(600, self._auto_sync_on_open)

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

        self._sync_before_quit()
        self.destroy()

    def _sync_before_quit(self):
        """Đồng bộ lần cuối (đồng bộ, có giới hạn thời gian ngắn) trước khi
        thoát — để thay đổi trong phiên làm việc chắc chắn lên Supabase mà
        không bắt người dùng phải nhớ bấm Sync tay. Timeout ngắn (8s) để
        không làm việc thoát app cảm giác bị treo; lỗi bị nuốt lặng lẽ, vì
        app đang đóng — lần mở sau sẽ tự sync bù lại."""
        config = get_sync_config()
        if config is None:
            return
        # Ưu tiên: bàn giao cho một TIẾN TRÌNH NGẦM tách rời — app đóng ngay, việc đồng bộ vẫn chạy tiếp
        # (không cửa sổ) cho tới khi xong rồi tự thoát. Khoá liên-tiến-trình chặn việc chạy chồng nếu bạn mở lại app.
        from infrastructure.sync_worker import spawn_detached
        self.withdraw()
        if spawn_detached():
            return
        logger.info("Không bật được tiến trình ngầm — đồng bộ ngay trong app trước khi thoát")
        # Chạy ở luồng nền; cửa sổ chính được ẩn ngay (cảm giác thoát tức thì) và một hộp nhỏ báo tiến trình
        # vẫn phản hồi — không còn cảnh cửa sổ "Not Responding" tới ~20 giây khi mạng chậm.
        import time as _time
        done = threading.Event()

        def _run():
            try:
                make_syncer(config, timeout=8.0, deadline_s=20.0).sync()
            except Exception as e:
                logger.info(f"Sync lúc thoát app không thành công (bỏ qua, sẽ tự sync lại lần mở sau): {e}")
            finally:
                done.set()

        threading.Thread(target=_run, daemon=True).start()
        note = None
        try:
            self.withdraw()
            note = ctk.CTkToplevel(self)
            note.overrideredirect(True)
            note.attributes("-topmost", True)
            ctk.CTkLabel(note, text="☁️  Đang đồng bộ lần cuối trước khi thoát…",
                         font=ctk.CTkFont(size=13), padx=22, pady=14).pack()
            note.update_idletasks()
            w, h = note.winfo_reqwidth(), note.winfo_reqheight()
            note.geometry(f"{w}x{h}+{(note.winfo_screenwidth() - w) // 2}+{(note.winfo_screenheight() - h) // 3}")
        except Exception:
            note = None
        end = _time.monotonic() + 22.0
        while not done.is_set() and _time.monotonic() < end:
            try:
                self.update()
            except Exception:
                break
            done.wait(0.05)
        try:
            if note is not None:
                note.destroy()
        except Exception:
            pass

    def _auto_sync_on_open(self):
        """Tự sync ngầm ngay sau khi mở app — không mở dialog, chỉ hiện
        toast nhỏ góc dưới-phải nếu có gì thay đổi hoặc nếu lỗi. Im lặng
        hoàn toàn nếu chưa cấu hình Supabase, hoặc nếu sync không có gì để
        đẩy/kéo (tránh làm phiền mỗi lần mở app)."""
        config = get_sync_config()
        if config is None or self._sync_in_progress:
            return

        self._sync_in_progress = True

        def _run():
            syncer = make_syncer(config)
            ok, stats, err = syncer.sync()
            call_in_ui(self, lambda: self._on_auto_sync_done(ok, stats, err))

        threading.Thread(target=_run, daemon=True).start()

    def _on_auto_sync_done(self, ok: bool, stats: dict, err: str):
        self._sync_in_progress = False
        if not self.winfo_exists():
            return

        if not ok:
            if (err or "").startswith("Đang có một lần đồng bộ khác"):
                return   # tiến trình ngầm (từ lần đóng app trước) còn đang đồng bộ — im lặng, lần mở sau sẽ bù
            SyncToast.show(
                self,
                message="⚠️  Chưa đồng bộ được — bấm để xem chi tiết",
                variant="error",
                on_click=self._open_sync,
            )
            return

        changed = (stats.get("pulled", 0) + stats.get("merged", 0) + stats.get("deleted_local", 0)
                   + len(stats.get("conflicts", [])))
        if changed <= 0:
            return  # không có gì thay đổi — im lặng, không làm phiền

        if hasattr(self, "table"):
            self.table.load_cards()
        if hasattr(self, "sidebar"):
            self.sidebar.refresh_stats()
            self.sidebar.refresh_decks()
        if hasattr(self, "stats") and self._current_tab == "stats":
            self.stats.refresh(force=True)
        if self._current_tab in ("grammar", "conj", "trans"):
            getattr(self, self._current_tab).refresh()

        SyncToast.show(
            self,
            message=f"☁️  Đã đồng bộ · {changed} thay đổi từ thiết bị khác",
            variant="success",
        )

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ── Top nav bar ──
        navbar = ctk.CTkFrame(self, corner_radius=0, height=46,
                               fg_color=("gray88", "gray15"))
        navbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        navbar.grid_propagate(False)
        # Cột 10 = spacer đẩy theme btn về bên phải
        

        ctk.CTkLabel(navbar, text="🇯🇵 日本語",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, padx=(10, 10), pady=6)

        tab_cfg  = dict(width=78, height=30, corner_radius=6, font=ctk.CTkFont(size=12))
        inactive = dict(fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"))
        col = [0]

        def put(btn, padx=1):
            col[0] += 1
            btn.grid(row=0, column=col[0], padx=padx, pady=6)
            return btn

        # Các màn hình (tab chính)
        self._tabs = {}
        for key, label in (("table", "🗂️ Thư viện"), ("grammar", "📖 Ngữ pháp"), ("conj", "活 Chia ĐT"),
                           ("trans", "訳 Bản dịch"), ("radicals", "🧩 Bộ thủ"), ("stats", "📊 Thống kê")):
            self._tabs[key] = put(ctk.CTkButton(navbar, text=label, **tab_cfg, **({} if key == "table" else inactive),
                                                command=lambda k=key: self._switch_tab(k)))
        self._tab_table = self._tabs["table"]
        self._tab_stats = self._tabs["stats"]
        self._tab_radicals = self._tabs["radicals"]

        review_btn = put(ctk.CTkButton(
            navbar, text="🎯 Ôn tập", **{**tab_cfg, "width": 76},
            fg_color="#E8A33D", hover_color="#C9862A", text_color="white",
            command=self._open_review_today
        ), padx=(10, 1))
        Tooltip(review_btn,
                "Ôn đúng những thẻ cần ôn lại hôm nay, dựa trên mức độ "
                "bạn đã nhớ chúng (lặp lại ngắt quãng - SRS).\n"
                "Thẻ dễ sẽ giãn cách ôn xa hơn, thẻ khó quay lại sớm hơn.")

        put(ctk.CTkButton(navbar, text="🃏 Thẻ", **{**tab_cfg, "width": 58}, **inactive, command=self._open_flashcard))
        put(ctk.CTkButton(navbar, text="📝 Quiz", **{**tab_cfg, "width": 62}, **inactive, command=self._open_quiz))
        put(ctk.CTkButton(navbar, text="⌨️ Gõ", **{**tab_cfg, "width": 58}, **inactive, command=self._open_typing))

        self._vk_toggle_btn = put(ctk.CTkButton(
            navbar, text="🈴", **{**tab_cfg, "width": 36}, **inactive,
            command=self._toggle_keyboard
        ))
        Tooltip(self._vk_toggle_btn,
                "Bật/tắt bàn phím ảo hiragana/katakana (F8).\n"
                "Nhấn phím trên bàn phím ảo sẽ gõ vào ô nhập liệu "
                "bạn vừa chọn — kể cả trong hộp thoại đang mở.")

        backup_btn = put(ctk.CTkButton(navbar, text="💾", **{**tab_cfg, "width": 36}, **inactive, command=self._open_backup))
        Tooltip(backup_btn, "Sao lưu / khôi phục dữ liệu (Ctrl+B)")

        # ── Nút Sync ──────────────────────────────────────────────────────────
        self._sync_btn = put(ctk.CTkButton(navbar, text="☁️ Sync", **{**tab_cfg, "width": 68}, **inactive, command=self._open_sync))
        navbar.grid_columnconfigure(col[0] + 1, weight=1)
        self._navbar_end = col[0] + 2

        # Theme toggle (bên phải cùng)
        ctk.CTkButton(
            navbar,
            text="☀️" if ctk.get_appearance_mode() == "Dark" else "🌙",
            width=26, height=26, corner_radius=13,
            fg_color="transparent", hover_color=("gray75", "gray35"),
            font=ctk.CTkFont(size=13), command=self._toggle_theme
        ).grid(row=0, column=self._navbar_end, padx=(2, 2), pady=6)
        help_btn = ctk.CTkButton(
            navbar, text="⌨", width=26, height=26, corner_radius=13,
            fg_color="transparent", hover_color=("gray75", "gray35"),
            font=ctk.CTkFont(size=14), command=self._open_shortcuts)
        help_btn.grid(row=0, column=self._navbar_end + 1, padx=(0, 8), pady=6)
        Tooltip(help_btn, "Bảng phím tắt (F1)")

        # ── Sidebar ──
        self.sidebar = Sidebar(self, self.card_service, self.deck_service, self.stats_service,
                                on_select_callback=self._on_filter_change)
        self.sidebar.grid(row=1, column=0, sticky="nsew")

        # ── Main content ──
        self.table = TableView(self, card_service=self.card_service, deck_service=self.deck_service,
                                decomposition_service=self.decomposition_service)
        self.table.grid(row=1, column=1, sticky="nsew")

        self.stats = StatsView(self, stats_service=self.stats_service)
        self.stats.grid(row=1, column=1, sticky="nsew")
        self.stats.grid_remove()

        self.radicals = RadicalView(self, card_service=self.card_service,
                                     radical_service=self.radical_service)
        self.radicals.grid(row=1, column=1, sticky="nsew")
        self.radicals.grid_remove()

        self.grammar = GrammarView(self, self.material_service)
        self.conj = ConjView(self, self.material_service)
        self.trans = TranslationsView(self, self.material_service, self.card_service, self.deck_service,
                                      grammar_view=self.grammar, on_cards_changed=self._on_cards_changed)
        for v in (self.grammar, self.conj, self.trans):
            v.grid(row=1, column=1, sticky="nsew")
            v.grid_remove()

        self.sidebar.activate_default()
        self._current_tab = "table"
        self._bind_shortcuts()

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _switch_tab(self, tab: str):
        if tab == self._current_tab:
            return
        self._current_tab = tab
        active   = dict(fg_color=("#3B8ED0", "#1F6AA5"), text_color="white")
        inactive = dict(fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"))

        # Hide everything, then show only what the target tab needs — avoids
        # an N-way if/elif matrix as more tabs get added.
        self.table.grid_remove()
        self.stats.grid_remove()
        self.radicals.grid_remove()
        self.grammar.grid_remove()
        self.conj.grid_remove()
        self.trans.grid_remove()
        self.sidebar.grid_remove()
        for btn in self._tabs.values():
            btn.configure(**inactive)

        if tab == "table":
            self.table.grid()
            self.sidebar.grid()
            self._tab_table.configure(**active)
        elif tab == "stats":
            self.stats.grid()
            self.stats.refresh()
            self._tab_stats.configure(**active)
        elif tab == "radicals":
            self.radicals.grid()
            self.radicals.refresh()
            self._tab_radicals.configure(**active)
        elif tab in ("grammar", "conj", "trans"):
            view = getattr(self, tab)
            view.grid()
            view.refresh()
            self._tabs[tab].configure(**active)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_cards_changed(self):
        """Thẻ mới được tạo từ màn Bản dịch → cập nhật thư viện + thanh bên."""
        if hasattr(self, "table"):
            self.table.load_cards()
        if hasattr(self, "sidebar"):
            self.sidebar.refresh_stats()
            self.sidebar.refresh_decks()

    def _bind_shortcuts(self):
        """Global keyboard shortcuts."""
        self.bind(KB_NEW_CARD, lambda _: (
            self._switch_tab("table") or self.table._add_card()))
        self.bind(KB_FOCUS_SEARCH, lambda _: (
            self._switch_tab("table") or self.table._focus_search()))
        self.bind(KB_REFRESH, lambda _: (
            self.table.load_cards() if self._current_tab == "table"
            else self.radicals.refresh() if self._current_tab == "radicals"
            else getattr(self, self._current_tab).refresh() if self._current_tab in ("grammar", "conj", "trans")
            else self.stats.refresh(force=True)))
        # bind_all (not bind): the keyboard is most useful while typing in a
        # child dialog (CardForm, TypingView...), which self.bind wouldn't reach.
        self.bind_all(KB_TOGGLE_KEYBOARD, lambda _: self._toggle_keyboard())
        # Phím tắt chuyển tab / mở công cụ (chỉ ở cửa sổ chính: self.bind, không lọt vào hộp thoại con)
        for seq, tab in ((KB_TAB_TABLE, "table"), (KB_TAB_STATS, "stats"), (KB_TAB_RADICALS, "radicals"),
                         (KB_TAB_GRAMMAR, "grammar"), (KB_TAB_CONJ, "conj"), (KB_TAB_TRANS, "trans")):
            self.bind(seq, lambda _, t=tab: self._switch_tab(t))
        for seq, fn in ((KB_REVIEW_TODAY, self._open_review_today), (KB_FLASHCARD, self._open_flashcard),
                        (KB_QUIZ, self._open_quiz), (KB_TYPING, self._open_typing),
                        (KB_BACKUP, self._open_backup), (KB_SYNC, self._open_sync)):
            self.bind(seq, lambda _, f=fn: self._kb_open(f))
        self.bind_all(KB_HELP, lambda _: self._open_shortcuts())

    def _kb_open(self, fn):
        """Mở công cụ bằng phím tắt — bỏ qua khi đang có hộp thoại modal, hoặc giữ phím (auto-repeat)."""
        import time
        now = time.monotonic()
        if now - getattr(self, "_kb_last", 0) < 0.6:
            return "break"
        grab = self.grab_current()
        if grab is not None and grab is not self:
            return "break"
        self._kb_last = now
        fn()
        return "break"

    def _open_shortcuts(self):
        if getattr(self, "_shortcuts_win", None) is not None and self._shortcuts_win.winfo_exists():
            self._shortcuts_win.destroy(); self._shortcuts_win = None
            return
        self._shortcuts_win = ShortcutsDialog(self)

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
        """Mở dialog sync Supabase."""
        if self._sync_in_progress:
            SyncToast.show(
                self,
                message="⏳  Đang tự động đồng bộ, vui lòng đợi giây lát...",
                variant="error",
            )
            return

        def on_done():
            # Reload table + stats sau khi sync xong
            if hasattr(self, "table"):
                self.table.load_cards()
            if hasattr(self, "sidebar"):
                self.sidebar.refresh_stats()
                self.sidebar.refresh_decks()
            if hasattr(self, "stats") and self._current_tab == "stats":
                self.stats.refresh(force=True)
            if self._current_tab in ("grammar", "conj", "trans"):
                getattr(self, self._current_tab).refresh()

        self._sync_in_progress = True
        dialog = SyncDialog(self, on_sync_done=on_done)
        dialog.bind("<Destroy>", lambda e: setattr(self, "_sync_in_progress", False), add="+")

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
