"""
domain/validators.py — Pure, GUI-free validation & data-shaping logic for
the card add/edit form.

This used to live inline inside ui/card_form.py's _save()/_auto_romaji(),
which meant it could only be exercised by driving the actual CustomTkinter
dialog. Extracting it here lets it be unit tested directly (see
tests/test_validators.py) and reused elsewhere (e.g. CSV/bulk import)
without touching any widget.

Lives in domain/ (not utils/) because it's business rule, not a generic
utility: it encodes what a "valid card" is and how form input maps to
stored data, independent of any UI toolkit or storage engine.
utils/validators.py re-exports this module unchanged so existing imports
keep working — see that file's docstring.
"""
import re

from constants import (
    TYPE_KANJI,
    MAX_CHARACTER_LEN, MAX_MEANING_LEN, MAX_READING_LEN,
    MAX_EXAMPLE_LEN, MAX_NOTES_LEN, MAX_SOURCE_LEN,
)

# Separators a user might type between multiple readings of the same kanji
# (e.g. 月 → on-yomi "getsu, gatsu" or "げつ/がつ"). Everything gets
# normalized to the app's canonical separator "、" so downstream features
# (kana quiz matching, CSV export, Anki export, search) all see one
# consistent format regardless of how the reading was typed.
_READING_SEPARATORS_RE = re.compile(r"[、,，/；;]+")


def truncate(value, max_len):
    """Trim a string to max_len characters. Falsy values pass through unchanged."""
    return value[:max_len] if value else value


def normalize_multi_reading(value: str) -> str:
    """
    Normalize a reading field that may contain multiple readings for one
    kanji (e.g. 月's on-yomi "getsu"/"gatsu", kun-yomi "tsuki").

    Accepts any common separator the user might type (",", "，", "/",
    ";", "、") and rewrites the value using "、" — the separator the rest
    of the app (typing practice, CSV/Anki export) already expects.
    Duplicate readings and stray whitespace are cleaned up; order of
    first appearance is preserved.
    """
    if not value:
        return value
    parts = _READING_SEPARATORS_RE.split(value)
    seen, out = set(), []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return "、".join(out)


def validate_required(character: str, meaning_vi: str) -> dict:
    """
    Check the two fields that are mandatory on every card.

    Returns a dict so the caller can highlight exactly which field(s)
    failed (mirrors the red-border behavior in CardForm._save()):
        {"character": bool, "meaning_vi": bool, "valid": bool}
    """
    char_ok = bool(character and character.strip())
    vi_ok = bool(meaning_vi and meaning_vi.strip())
    return {"character": char_ok, "meaning_vi": vi_ok, "valid": char_ok and vi_ok}


def resolve_romaji_source(card_type: str, on_reading: str = "", kun_reading: str = "",
                           kana_reading: str = "", character: str = "") -> str:
    """
    Decide which raw text should be fed into kana_to_romaji() for the
    "⚡ Tự tạo" (auto-generate romaji) button, based on card type.

    Priority mirrors the original CardForm._auto_romaji():
      - kanji:  kun-yomi, falling back to on-yomi
      - other:  the kana reading field
      - final fallback (any type): the main character itself
    """
    if card_type == TYPE_KANJI:
        kana = (kun_reading or "").strip() or (on_reading or "").strip()
    else:
        kana = (kana_reading or "").strip()
    return kana or (character or "").strip()


_POS_ALIAS = {
    "danh từ": "noun", "danh tu": "noun", "meishi": "noun", "n": "noun",
    "động từ": "verb", "dong tu": "verb", "doushi": "verb", "verb": "verb",
    "đại từ": "pronoun", "dai tu": "pronoun", "daimeishi": "pronoun",
    "trợ từ": "particle", "tro tu": "particle", "joshi": "particle",
    "trạng từ": "adverb", "trang tu": "adverb", "fukushi": "adverb",
    "liên từ": "conjunction", "lien tu": "conjunction", "setsuzokushi": "conjunction",
    "thán từ": "interjection", "than tu": "interjection", "kandoushi": "interjection",
    "động từ nhóm 1": "verb1", "dong tu nhom 1": "verb1", "nhóm 1": "verb1", "godan": "verb1", "group 1": "verb1", "v1": "verb1", "verb 1": "verb1",
    "động từ nhóm 2": "verb2", "dong tu nhom 2": "verb2", "nhóm 2": "verb2", "ichidan": "verb2", "group 2": "verb2", "v2": "verb2", "verb 2": "verb2",
    "động từ nhóm 3": "verb3", "dong tu nhom 3": "verb3", "nhóm 3": "verb3", "group 3": "verb3", "v3": "verb3", "verb 3": "verb3", "irregular": "verb3",
    "tính từ đuôi い": "adj_i", "tính từ đuôi i": "adj_i", "tinh tu duoi i": "adj_i", "i-adj": "adj_i", "i adj": "adj_i", "adj-i": "adj_i",
    "tính từ đuôi な": "adj_na", "tính từ đuôi na": "adj_na", "tinh tu duoi na": "adj_na", "na-adj": "adj_na", "na adj": "adj_na", "adj-na": "adj_na",
}


def normalize_pos(value):
    """Mã từ loại chuẩn (noun/verb1/verb2/verb3/adj_i/adj_na) từ mã hoặc tên gọi quen thuộc; không nhận ra → None."""
    from constants import CARD_POS
    s = str(value or "").strip().lower()
    if s in CARD_POS:
        return s
    return _POS_ALIAS.get(s)


def build_card_data(*, card_type, character, meaning_vi,
                     reading_on=None, reading_kun=None, reading_kana=None,
                     reading_hanviet=None,
                     romaji="", meaning_en="", example_jp="", example_vi="",
                     jlpt_level="", status="new", is_favorite=False,
                     source="", notes="", stroke_count=None, pos=None,
                     audio_path=None, image_path=None) -> dict:
    """
    Build the exact dict shape expected by database.models.add_card() /
    update_card(), applying strip + max-length truncation consistently.

    Reading fields (`reading_on`/`reading_kun`/`reading_kana`) use `None`
    as a sentinel meaning "this field's widget doesn't exist for this
    card type" (e.g. no on/kun-yomi fields for a vocab card) — this
    matches CardForm, where those fields are only built for relevant
    types. Pass an empty string (not None) if the widget exists but is
    simply empty.

    Caller should run validate_required() first; this function does not
    itself enforce that character/meaning_vi are non-empty.
    """
    t = truncate

    def _reading(value):
        if value is None:
            return None
        return t(normalize_multi_reading(value.strip()), MAX_READING_LEN)

    return {
        "type":            card_type,
        "character":       t((character or "").strip(), MAX_CHARACTER_LEN),
        "reading_on":      _reading(reading_on),
        "reading_kun":     _reading(reading_kun),
        "reading_kana":    _reading(reading_kana),
        "reading_hanviet": (t((reading_hanviet or "").strip(), MAX_READING_LEN) or None)
                           if reading_hanviet is not None else None,
        "romaji":       t((romaji or "").strip(), MAX_READING_LEN) or None,
        "meaning_vi":   t((meaning_vi or "").strip(), MAX_MEANING_LEN),
        "meaning_en":   t((meaning_en or "").strip(), MAX_MEANING_LEN) or None,
        "example_jp":   t((example_jp or "").strip(), MAX_EXAMPLE_LEN) or None,
        "example_vi":   t((example_vi or "").strip(), MAX_EXAMPLE_LEN) or None,
        "stroke_count": stroke_count,
        "jlpt_level":   jlpt_level or None,
        "status":       status,
        "is_favorite":  1 if is_favorite else 0,
        "source":       t((source or "").strip(), MAX_SOURCE_LEN) or None,
        "notes":        t((notes or "").strip(), MAX_NOTES_LEN) or None,
        "pos":          normalize_pos(pos),
        "audio_path":   audio_path,
        "image_path":   image_path,
    }
