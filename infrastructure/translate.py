"""
infrastructure/translate.py — English → Vietnamese translation suggestion.

Uses the free MyMemory API (https://mymemory.translated.net, no API key
required). Same async + cache shape as infrastructure/jisho.py, for the
same reason: card_form.py's Jisho lookup fills every field except
meaning_vi (Jisho has no Vietnamese) — this gives the user a one-click
*suggestion* for that field from the English gloss Jisho already
returned, without them needing to leave the app.

Deliberately a suggestion, not an auto-fill: MyMemory is a free
crowd-sourced/machine translation service, good enough to save typing on
common words but wrong often enough on ambiguous or idiomatic ones that
silently writing it into meaning_vi (a required field people rely on to
actually learn the word) would do more harm than good. The UI shows the
suggestion and requires an explicit click to accept it.
"""
import urllib.request
import urllib.parse
import json
import threading
import time
import logging

logger = logging.getLogger(__name__)

# ── In-memory cache — same shape as jisho.py's, deliberately not shared
# (different keys, different TTL: translations of short English words
# don't change, so a longer TTL than Jisho's word-lookup cache is fine).
_CACHE: dict = {}
_CACHE_TTL = 3600     # seconds (1h)
_CACHE_MAX = 200


def _cache_get(text: str):
    entry = _CACHE.get(text.lower())
    if entry and (time.time() - entry[1]) < _CACHE_TTL:
        return entry[0]
    return None


def _cache_set(text: str, translation: str):
    if len(_CACHE) >= _CACHE_MAX:
        oldest = min(_CACHE, key=lambda k: _CACHE[k][1])
        del _CACHE[oldest]
    _CACHE[text.lower()] = (translation, time.time())


def clear_cache():
    _CACHE.clear()


def suggest_vi(en_text: str, callback):
    """
    Async EN→VI translation suggestion — runs in a thread, calls
    callback(translation, error) when done.
    translation: str, or None on error/empty input.
    error: str or None.
    """
    en_text = (en_text or "").strip()
    if not en_text:
        threading.Thread(target=lambda: callback(None, None), daemon=True).start()
        return

    cached = _cache_get(en_text)
    if cached is not None:
        threading.Thread(target=lambda: callback(cached, None), daemon=True).start()
        return

    def _run():
        try:
            encoded = urllib.parse.quote(en_text)
            url = (f"https://api.mymemory.translated.net/get"
                   f"?q={encoded}&langpair=en|vi")
            req = urllib.request.Request(url, headers={"User-Agent": "JapaneseStudyApp/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            translation = (data.get("responseData", {}) or {}).get("translatedText", "").strip()
            if not translation:
                callback(None, "Không có kết quả dịch")
                return
            _cache_set(en_text, translation)
            logger.info(f"Translate fetched: '{en_text}' → '{translation}'")
            callback(translation, None)
        except Exception as ex:
            logger.warning(f"Translate error for '{en_text}': {ex}")
            callback(None, str(ex))

    threading.Thread(target=_run, daemon=True).start()
