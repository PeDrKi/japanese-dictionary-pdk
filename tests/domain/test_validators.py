"""
Tests for domain/validators.py — pure logic extracted from ui/card_form.py.
No GUI/tkinter needed, so these run fast and everywhere (CI included).
"""
from domain.validators import (
    truncate, validate_required, resolve_romaji_source, build_card_data,
)
from constants import MAX_CHARACTER_LEN, MAX_MEANING_LEN, MAX_READING_LEN


# ── truncate ──────────────────────────────────────────────────────────────────

def test_truncate_cuts_long_string():
    assert truncate("a" * 300, 10) == "a" * 10


def test_truncate_leaves_short_string_untouched():
    assert truncate("abc", 10) == "abc"


def test_truncate_passes_falsy_values_through():
    assert truncate("", 10) == ""
    assert truncate(None, 10) is None


# ── validate_required ────────────────────────────────────────────────────────

def test_validate_required_ok_when_both_present():
    r = validate_required("犬", "con chó")
    assert r == {"character": True, "meaning_vi": True, "valid": True}


def test_validate_required_fails_when_character_missing():
    r = validate_required("", "con chó")
    assert r["character"] is False
    assert r["meaning_vi"] is True
    assert r["valid"] is False


def test_validate_required_fails_when_meaning_missing():
    r = validate_required("犬", "")
    assert r["character"] is True
    assert r["meaning_vi"] is False
    assert r["valid"] is False


def test_validate_required_fails_on_whitespace_only():
    r = validate_required("   ", "   ")
    assert r["valid"] is False


def test_validate_required_fails_when_both_missing():
    r = validate_required(None, None)
    assert r == {"character": False, "meaning_vi": False, "valid": False}


# ── resolve_romaji_source ─────────────────────────────────────────────────────

def test_romaji_source_kanji_prefers_kun_over_on():
    assert resolve_romaji_source("kanji", on_reading="アメ", kun_reading="あめ") == "あめ"


def test_romaji_source_kanji_falls_back_to_on_when_no_kun():
    assert resolve_romaji_source("kanji", on_reading="アメ", kun_reading="") == "アメ"


def test_romaji_source_non_kanji_uses_kana_reading():
    assert resolve_romaji_source("vocab", kana_reading="たべる") == "たべる"


def test_romaji_source_falls_back_to_character_when_nothing_else():
    assert resolve_romaji_source("hiragana", kana_reading="", character="あ") == "あ"


def test_romaji_source_empty_when_nothing_available():
    assert resolve_romaji_source("vocab") == ""


# ── build_card_data ───────────────────────────────────────────────────────────

def test_build_card_data_basic_shape():
    data = build_card_data(
        card_type="vocab", character="犬 ", meaning_vi=" con chó ",
        reading_kana="いぬ", romaji="inu", meaning_en="dog",
    )
    assert data["type"] == "vocab"
    assert data["character"] == "犬"          # stripped
    assert data["meaning_vi"] == "con chó"    # stripped
    assert data["reading_kana"] == "いぬ"
    assert data["romaji"] == "inu"
    assert data["meaning_en"] == "dog"
    assert data["is_favorite"] == 0
    assert data["status"] == "new"


def test_build_card_data_none_reading_means_field_not_applicable():
    """None (widget didn't exist for this card type) must stay None,
    not become an empty string."""
    data = build_card_data(
        card_type="hiragana", character="あ", meaning_vi="âm a",
        reading_on=None, reading_kun=None, reading_kana="a",
    )
    assert data["reading_on"] is None
    assert data["reading_kun"] is None
    assert data["reading_kana"] == "a"


def test_build_card_data_empty_string_reading_stays_empty_not_none():
    """Widget existed but user left it blank -> "" is preserved (matches
    the original CardForm behavior, which did NOT apply `or None` to
    reading_on/kun/kana)."""
    data = build_card_data(
        card_type="kanji", character="雨", meaning_vi="mưa",
        reading_on="", reading_kun="あめ",
    )
    assert data["reading_on"] == ""
    assert data["reading_kun"] == "あめ"


def test_build_card_data_optional_text_fields_blank_become_none():
    """romaji/meaning_en/example_*/source/notes DO fall back to None
    when blank (matches the `or None` pattern in the original code)."""
    data = build_card_data(
        card_type="vocab", character="犬", meaning_vi="con chó",
        romaji="", meaning_en="", example_jp="", example_vi="",
        source="", notes="",
    )
    for field in ("romaji", "meaning_en", "example_jp", "example_vi", "source", "notes"):
        assert data[field] is None, field


def test_build_card_data_favorite_flag_converted_to_int():
    assert build_card_data(
        card_type="vocab", character="犬", meaning_vi="chó", is_favorite=True
    )["is_favorite"] == 1
    assert build_card_data(
        card_type="vocab", character="犬", meaning_vi="chó", is_favorite=False
    )["is_favorite"] == 0


def test_build_card_data_empty_jlpt_becomes_none():
    data = build_card_data(card_type="vocab", character="犬", meaning_vi="chó", jlpt_level="")
    assert data["jlpt_level"] is None


def test_build_card_data_truncates_long_character():
    data = build_card_data(
        card_type="vocab", character="a" * 500, meaning_vi="chó",
    )
    assert len(data["character"]) == MAX_CHARACTER_LEN


def test_build_card_data_truncates_long_meaning():
    data = build_card_data(
        card_type="vocab", character="犬", meaning_vi="a" * 999,
    )
    assert len(data["meaning_vi"]) == MAX_MEANING_LEN


def test_build_card_data_truncates_long_reading():
    data = build_card_data(
        card_type="vocab", character="犬", meaning_vi="chó",
        reading_kana="a" * 999,
    )
    assert len(data["reading_kana"]) == MAX_READING_LEN


def test_build_card_data_is_compatible_with_add_card(fresh_db):
    """End-to-end: data shaped by build_card_data() must be directly
    accepted by models.add_card() with no KeyError/DBError."""
    from database import models
    data = build_card_data(
        card_type="vocab", character="猫", meaning_vi="con mèo",
        reading_kana="ねこ", romaji="neko", meaning_en="cat",
        jlpt_level="N5", status="new", is_favorite=True, source="test",
    )
    card_id = models.add_card(data)
    saved = models.get_card_by_id(card_id)
    assert saved["character"] == "猫"
    assert saved["is_favorite"] == 1
