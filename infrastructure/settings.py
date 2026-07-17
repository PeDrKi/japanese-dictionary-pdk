"""
infrastructure/settings.py — Persistent app settings stored in
settings.json next to the database. Covers: window geometry, last theme,
last tab, UI preferences. Moved from utils/ (Stage: utils/ cleanup) since
this does real file I/O.
"""
import json
import os
import logging

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


def set(key: str, value):
    s = load()
    s[key] = value
    _save(s)


def update(data: dict):
    s = load()
    s.update(data)
    _save(s)


def _save(data: dict):
    global _cache
    _cache = data
    try:
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Could not save settings: {e}")
