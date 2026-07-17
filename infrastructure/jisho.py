"""
infrastructure/jisho.py — Jisho.org public API wrapper.
Endpoint: https://jisho.org/api/v1/search/words?keyword=<query>
No API key required. Moved from utils/ (Stage: utils/ cleanup) since this
does real network I/O.
"""
import urllib.request
import urllib.parse
import json
import threading
import time
import logging

logger = logging.getLogger(__name__)

# ── In-memory LRU cache ───────────────────────────────────────────────────────
_CACHE: dict = {}          # keyword → (results, timestamp)
_CACHE_TTL   = 600         # seconds (10 min)
_CACHE_MAX   = 100         # max entries


def _cache_get(keyword: str):
    entry = _CACHE.get(keyword.lower())
    if entry and (time.time() - entry[1]) < _CACHE_TTL:
        logger.debug(f"Jisho cache hit: {keyword}")
        return entry[0]
    return None


def _cache_set(keyword: str, results):
    if len(_CACHE) >= _CACHE_MAX:
        # Evict oldest entry
        oldest = min(_CACHE, key=lambda k: _CACHE[k][1])
        del _CACHE[oldest]
    _CACHE[keyword.lower()] = (results, time.time())


def clear_cache():
    _CACHE.clear()


def search(keyword: str, callback):
    """
    Async search with cache — runs in a thread, calls callback(results, error) when done.
    results: list of JishoEntry dicts, or [] on error.
    error: str or None
    """
    # Check cache — deliver via thread to keep callback path consistent
    cached = _cache_get(keyword)
    if cached is not None:
        threading.Thread(target=lambda: callback(cached, None), daemon=True).start()
        return

    def _run():
        try:
            encoded = urllib.parse.quote(keyword)
            url = f"https://jisho.org/api/v1/search/words?keyword={encoded}"
            req = urllib.request.Request(url, headers={"User-Agent": "JapaneseStudyApp/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = [_parse(e) for e in data.get("data", [])[:8]]
            _cache_set(keyword, results)
            logger.info(f"Jisho fetched: {keyword} → {len(results)} results")
            callback(results, None)
        except Exception as ex:
            logger.warning(f"Jisho error for '{keyword}': {ex}")
            callback([], str(ex))

    threading.Thread(target=_run, daemon=True).start()


def _parse(entry: dict) -> dict:
    """Flatten one Jisho entry into a simple dict."""
    japanese = entry.get("japanese", []) if isinstance(entry, dict) else []
    senses   = entry.get("senses",   []) if isinstance(entry, dict) else []

    # Safely get first japanese entry
    first_jp = japanese[0] if japanese and isinstance(japanese[0], dict) else {}
    word     = first_jp.get("word", "")
    reading  = first_jp.get("reading", "")

    # Collect English glosses — items are plain strings e.g. ["rain", "rainfall"]
    en_glosses = []
    for s in senses:
        for g in s.get("english_definitions", []):
            if isinstance(g, str):
                en_glosses.append(g)
            elif isinstance(g, dict):
                en_glosses.append(g.get("value", "") or g.get("text", "") or str(g))
    meaning_en = ", ".join(g for g in en_glosses[:4] if g)

    # JLPT — Jisho returns e.g. ["jlpt-n5"]
    jlpt = ""
    for tag in entry.get("jlpt", []):
        jlpt = tag.replace("jlpt-", "").upper()   # "jlpt-n5" → "N5"
        break

    # Part of speech
    pos_list = []
    for s in senses:
        pos_list.extend(s.get("parts_of_speech", []))
    pos = pos_list[0] if pos_list else ""

    # is_common
    is_common = entry.get("is_common", False)

    # All readings (for display in picker)
    alt_forms = [
        {"word": j.get("word",""), "reading": j.get("reading","")}
        for j in japanese if isinstance(j, dict)
    ]

    return {
        "word":       word or reading,
        "reading":    reading,
        "meaning_en": meaning_en,
        "jlpt":       jlpt,
        "pos":        pos,
        "is_common":  is_common,
        "alt_forms":  alt_forms,
        "raw":        entry,   # keep full entry for later use
    }


def guess_type(entry: dict) -> str:
    """Guess card type from a parsed entry."""
    word = entry.get("word", "")
    pos  = entry.get("pos",  "").lower()

    # Pure kana checks
    hiragana = set("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽゃゅょっー")
    katakana = set("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポャュョッー")

    if word and all(c in hiragana for c in word):
        return "hiragana"
    if word and all(c in katakana for c in word):
        return "katakana"

    # Has kanji + no extra word form → likely standalone kanji
    has_kanji = any('\u4e00' <= c <= '\u9fff' for c in word)
    if has_kanji and len(word) == 1:
        return "kanji"

    return "vocab"
