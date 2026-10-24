"""Tiến trình đồng bộ chạy ngầm sau khi đóng app (không cửa sổ, không cần giao diện).

Chạy:  python main.pyw --sync-only   (app tự gọi khi thoát)
Tự thoát ngay khi sync xong hoặc quá hạn."""
import logging
import sys

logger = logging.getLogger("sync_worker")


def run(deadline_s: float = 120.0, wait_lock_s: float = 30.0) -> int:
    from infrastructure.cloud_config import get_saved_config, make_syncer
    cfg = get_saved_config()
    if cfg is None:
        return 0
    try:
        ok, stats, err = make_syncer(cfg, timeout=20.0, deadline_s=deadline_s, wait_lock_s=wait_lock_s).sync()
    except Exception as e:   # không bao giờ để tiến trình ngầm nổ ra màn hình
        logger.exception("Sync ngầm lỗi: %s", e)
        return 1
    if ok:
        logger.info("Sync ngầm sau khi đóng app: xong (đẩy %s, kéo %s)", stats.get("pushed"), stats.get("pulled"))
        return 0
    logger.info("Sync ngầm sau khi đóng app không thành công: %s", err)
    return 1


def spawn_detached() -> bool:
    """Bật tiến trình sync ngầm tách khỏi app. True nếu khởi động được."""
    import os
    import subprocess
    try:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--sync-only"]
        else:
            exe = sys.executable
            if os.name == "nt":
                w = os.path.join(os.path.dirname(exe), "pythonw.exe")
                if os.path.exists(w):
                    exe = w
            main = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "main.pyw"))
            cmd = [exe, main, "--sync-only"]
        kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                  cwd=os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
        if os.name == "nt":
            kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
        else:
            kw["start_new_session"] = True
        subprocess.Popen(cmd, **kw)
        return True
    except Exception as e:
        logger.warning("Không bật được sync ngầm: %s", e)
        return False
