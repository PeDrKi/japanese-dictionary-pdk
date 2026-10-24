"""Gọi code giao diện từ luồng nền một cách an toàn.

Tkinter không an toàn với luồng: gọi widget.after()/winfo_exists() từ luồng nền
đôi khi gây "main thread is not in main loop" hoặc treo khi cửa sổ đang đóng.
Luồng nền chỉ việc `call_in_ui(widget, fn)` — hàm được xếp vào hàng đợi và luồng
giao diện tự lấy ra chạy (bỏ qua nếu widget đã bị đóng)."""
import logging
import queue
import tkinter as tk

logger = logging.getLogger(__name__)
_q: "queue.SimpleQueue" = queue.SimpleQueue()
_root = None


def install(root, interval_ms: int = 40):
    """Gọi 1 lần ở luồng giao diện (App.__init__) để bắt đầu nhận việc từ hàng đợi."""
    global _root
    _root = root

    def _poll():
        while True:
            try:
                widget, fn = _q.get_nowait()
            except queue.Empty:
                break
            try:
                if widget is None or widget.winfo_exists():
                    fn()
            except tk.TclError:
                pass
            except Exception:
                logger.exception("Lỗi khi chạy callback giao diện từ luồng nền")
        try:
            root.after(interval_ms, _poll)
        except tk.TclError:
            pass   # cửa sổ đã đóng

    root.after(interval_ms, _poll)


def call_in_ui(widget, fn):
    """An toàn khi gọi từ BẤT KỲ luồng nào."""
    _q.put((widget, fn))
