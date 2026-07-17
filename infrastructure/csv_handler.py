"""
infrastructure/csv_handler.py — CSV import/export for cards.
Moved from utils/ (Stage: utils/ cleanup) since this does real file I/O.
"""
import csv, os
from domain.validators import normalize_multi_reading, truncate
from constants import (
    MAX_CHARACTER_LEN, MAX_READING_LEN, MAX_MEANING_LEN,
    MAX_EXAMPLE_LEN, MAX_NOTES_LEN, MAX_SOURCE_LEN,
)

FIELDS = ["type","character","reading_on","reading_kun","reading_kana","reading_hanviet",
          "romaji","meaning_vi","meaning_en","example_jp","example_vi",
          "stroke_count","jlpt_level","status","is_favorite","source","notes"]


def export_csv(cards, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(cards)
    return len(cards)


def _s(row, key, default=""):
    """Safely read+strip a DictReader field. A short/malformed CSV row
    can make csv.DictReader map a present key to `None` (not just make
    the key absent) — plain `row.get(key, default).strip()` then raises
    AttributeError and aborts the whole import. This never does."""
    v = row.get(key, default)
    return (v or default).strip() if isinstance(v, str) or v is None else str(v).strip()


def import_csv(filepath):
    valid, errors = [], []
    if not os.path.exists(filepath):
        return [], [(-1, "File không tồn tại")]
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), 2):
            try:
                character = _s(row, "character")
                meaning_vi = _s(row, "meaning_vi")
                if not character:
                    errors.append((i, "Thiếu 'character'")); continue
                if not meaning_vi:
                    errors.append((i, "Thiếu 'meaning_vi'")); continue
                t = _s(row, "type", "vocab").lower()
                if t not in ("kanji","hiragana","katakana","vocab"):
                    errors.append((i, f"type không hợp lệ: {t}")); continue
                valid.append({
                    "type": t,
                    "character":    truncate(character, MAX_CHARACTER_LEN),
                    "reading_on":   truncate(normalize_multi_reading(_s(row, "reading_on")), MAX_READING_LEN) or None,
                    "reading_kun":  truncate(normalize_multi_reading(_s(row, "reading_kun")), MAX_READING_LEN) or None,
                    "reading_kana": truncate(_s(row, "reading_kana"), MAX_READING_LEN) or None,
                    "reading_hanviet": truncate(_s(row, "reading_hanviet"), MAX_READING_LEN) or None,
                    "romaji":       truncate(_s(row, "romaji"), MAX_READING_LEN) or None,
                    "meaning_vi":   truncate(meaning_vi, MAX_MEANING_LEN),
                    "meaning_en":   truncate(_s(row, "meaning_en"), MAX_MEANING_LEN) or None,
                    "example_jp":   truncate(_s(row, "example_jp"), MAX_EXAMPLE_LEN) or None,
                    "example_vi":   truncate(_s(row, "example_vi"), MAX_EXAMPLE_LEN) or None,
                    "stroke_count": _int(row.get("stroke_count")),
                    "jlpt_level":   _s(row, "jlpt_level").upper() or None,
                    "status":       _s(row, "status", "new") or "new",
                    "is_favorite":  1 if _s(row, "is_favorite", "0") == "1" else 0,
                    "source":       truncate(_s(row, "source"), MAX_SOURCE_LEN) or None,
                    "notes":        truncate(_s(row, "notes"), MAX_NOTES_LEN) or None,
                    "audio_path": None, "image_path": None,
                })
            except Exception as e:
                errors.append((i, f"Lỗi không xác định: {e}"))
    return valid, errors


def get_csv_template_path(folder):
    path = os.path.join(folder, "template_import.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerow({"type":"kanji","character":"雨","reading_on":"ウ",
                    "reading_kun":"あめ、あま","reading_kana":"","reading_hanviet":"vũ","romaji":"ame",
                    "meaning_vi":"mưa","meaning_en":"rain","example_jp":"雨が降る",
                    "example_vi":"Trời mưa","stroke_count":"8","jlpt_level":"N5",
                    "status":"new","is_favorite":"0","source":"Minna no Nihongo","notes":""})
    return path


def _int(v):
    try: return int(v)
    except (TypeError, ValueError): return None
