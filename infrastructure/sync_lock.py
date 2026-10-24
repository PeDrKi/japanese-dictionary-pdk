"""Khoá đồng bộ giữa NHIỀU tiến trình (app chính ↔ tiến trình sync chạy ngầm sau khi đóng app).

Khoá là một file tạo bằng O_EXCL cạnh database; ghi PID + thời điểm. Khoá "chết" (tiến trình đã tắt,
hoặc quá cũ) được tự dọn để không bao giờ kẹt vĩnh viễn."""
import os
import time

STALE_S = 600.0   # một lần sync không bao giờ hợp lệ lâu hơn thế


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return True   # không chắc → coi như còn sống, dựa vào STALE_S
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            pid_s, ts_s = f.read().split()[:2]
        return int(pid_s), float(ts_s)
    except Exception:
        return 0, 0.0


def acquire(path: str, wait_s: float = 0.0):
    """→ token (dùng cho release) hoặc None nếu tiến trình khác đang giữ khoá."""
    end = time.monotonic() + max(0.0, wait_s)
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()} {time.time()}")
            return path
        except FileExistsError:
            pid, ts = _read(path)
            if pid == os.getpid():
                return None   # chính tiến trình này đã giữ (khoá luồng sẽ chặn trước, phòng hờ)
            if not _pid_alive(pid) or (time.time() - ts) > STALE_S:
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
        except OSError:
            return path   # không tạo được file khoá (thư mục chỉ đọc…) → không chặn đồng bộ
        if time.monotonic() >= end:
            return None
        time.sleep(0.3)


def release(token):
    if token:
        try:
            pid, _ = _read(token)
            if pid == os.getpid():
                os.remove(token)
        except OSError:
            pass
