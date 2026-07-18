import sys, os, logging
sys.path.insert(0, os.path.dirname(__file__))

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_PATH = os.path.join(os.path.dirname(__file__), "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

from database.db import init_db, check_and_repair
from ui.app import App
from application.stats_service import StatsService
from application.card_service import CardService
from application.deck_service import DeckService
from application.study_service import StudyService
from application.decomposition_service import DecompositionService
from application.radical_service import RadicalService
from infrastructure.db.sqlite_repositories import (
    SqliteStatsRepository, SqliteCardRepository, SqliteDeckRepository,
    SqliteStudySessionRepository, SqliteRadicalRepository, SqliteUserDecompositionRepository,
)
from infrastructure.kanji_ids import FileKanjiIdsRepository


def main():
    logger.info("App starting...")

    # ── Integrity check before anything else ──────────────────────────────────
    was_ok, integrity_msg = check_and_repair()
    if not was_ok:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning("Cảnh báo Database", integrity_msg)
        root.destroy()
        logger.warning(f"DB integrity issue: {integrity_msg}")

    try:
        init_db()
    except Exception as e:
        logger.critical(f"Failed to init DB: {e}")
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Lỗi khởi động",
            f"Không thể khởi tạo database:\n{e}\n\nKiểm tra file app.log.")
        sys.exit(1)

    # ── Composition root: wire concrete implementations here, nowhere else ──
    stats_service         = StatsService(SqliteStatsRepository())
    card_service          = CardService(SqliteCardRepository())
    deck_service          = DeckService(SqliteDeckRepository())
    study_service         = StudyService(SqliteStudySessionRepository())
    decomposition_service = DecompositionService(FileKanjiIdsRepository(), SqliteUserDecompositionRepository())
    radical_service        = RadicalService(SqliteRadicalRepository())

    app = App(stats_service=stats_service, card_service=card_service,
              deck_service=deck_service, study_service=study_service,
              decomposition_service=decomposition_service,
              radical_service=radical_service)
    app.mainloop()
    logger.info("App closed.")


if __name__ == "__main__":
    main()
