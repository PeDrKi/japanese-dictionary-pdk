"""
infrastructure/settings.py — Persistent app settings stored in
settings.json next to the database. Covers: window geometry, last theme,
last tab, UI preferences. Moved from utils/ (Stage: utils/ cleanup) since
this does real file I/O.
"""
import json
import os
import logging
import threading

logger   = logging.getLogger(__name__)
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "settings.json")
_SETTINGS_PATH = os.path.normpath(_SETTINGS_PATH)

_DEFAULTS = {
    "theme":        "dark",
    "window_geo":   "1280x760",
    "window_x":     None,
    "window_y":     None,
    "last_tab":     "table",
    "page_size":    20,
    "detail_panel": True,
}

_cache: dict = {}
_lock = threading.RLock()   # token làm mới ghi từ luồng đồng bộ, UI ghi từ luồng chính


def load() -> dict:
    global _cache
    if _cache:
        return _cache
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache = {**_DEFAULTS, **data}
    except FileNotFoundError:
        _cache = dict(_DEFAULTS)   # normal on first run — nothing to log
    except Exception as e:
        logger.warning(f"Could not load settings ({_SETTINGS_PATH}), using defaults: {e}")
        _cache = dict(_DEFAULTS)
    return _cache


def get(key: str, default=None):
    return load().get(key, default)


def _reload():
    """Đọc lại file trước khi ghi: tiến trình sync ngầm có thể vừa xoay refresh token — không được ghi đè bằng bản cũ trong bộ nhớ."""
    global _cache
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            _cache = {**_DEFAULTS, **json.load(f)}
    except FileNotFoundError:
        pass
    except Exception:
        pass   # file hỏng/đang ghi dở → dùng bản trong bộ nhớ
    return load()


def set(key: str, value):
    with _lock:
        s = _reload()
        s[key] = value
        _save(s)


def update(data: dict):
    with _lock:
        s = _reload()
        s.update(data)
        _save(s)


def _save(data: dict):
    global _cache
    _cache = data
    try:
        tmp = _SETTINGS_PATH + ".tmp"            # ghi file tạm rồi đổi tên: mất điện giữa chừng không làm hỏng settings.json
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _SETTINGS_PATH)
    except Exception as e:
        logger.warning(f"Could not save settings: {e}")
