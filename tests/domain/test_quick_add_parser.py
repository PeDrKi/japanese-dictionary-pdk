"""
Tests for domain/quick_add_parser.py.
"""
from domain.quick_add_parser import parse_line, parse_quick_add_text


# ── parse_line: valid formats ────────────────────────────────────────────────

def test_dash_with_spaces():
    r = parse_line("猫 - con mèo")
    assert r == {"character": "猫", "meaning_vi": "con mèo", "raw": "猫 - con mèo",
                 "valid": True, "error": None}


def test_dash_no_spaces():
    r = parse_line("猫-con mèo")
    assert r["character"] == "猫"
    assert r["meaning_vi"] == "con mèo"
    assert r["valid"] is True


def test_colon_with_space():
    r = parse_line("犬: con chó")
    assert r["character"] == "犬"
    assert r["meaning_vi"] == "con chó"
    assert r["valid"] is True


def test_colon_no_space():
    r = parse_line("犬:con chó")
    assert r["character"] == "犬"
    assert r["meaning_vi"] == "con chó"


def test_tab_separator():
    r = parse_line("食べる\tăn")
    assert r["character"] == "食べる"
    assert r["meaning_vi"] == "ăn"
    assert r["valid"] is True


def test_en_dash_and_em_dash():
    assert parse_line("猫 – con mèo")["meaning_vi"] == "con mèo"
    assert parse_line("猫 — con mèo")["meaning_vi"] == "con mèo"


def test_only_first_separator_splits_meaning_with_dash_kept_intact():
    r = parse_line("犬 - giống chó - shiba")
    assert r["character"] == "犬"
    assert r["meaning_vi"] == "giống chó - shiba"
    assert r["valid"] is True


def test_leading_trailing_whitespace_stripped():
    r = parse_line("  猫  -  con mèo  ")
    assert r["character"] == "猫"
    assert r["meaning_vi"] == "con mèo"


# ── parse_line: invalid / edge cases ─────────────────────────────────────────

def test_character_only_no_separator_is_invalid():
    r = parse_line("猫")
    assert r["character"] == "猫"
    assert r["meaning_vi"] == ""
    assert r["valid"] is False
    assert r["error"] == "Thiếu nghĩa tiếng Việt"


def test_blank_line_is_invalid():
    r = parse_line("   ")
    assert r["valid"] is False
    assert r["error"] == "Dòng trống"


def test_empty_string_is_invalid():
    r = parse_line("")
    assert r["valid"] is False
    assert r["error"] == "Dòng trống"


def test_separator_with_nothing_before_it_is_invalid():
    r = parse_line(" - con mèo")
    assert r["character"] == ""
    assert r["valid"] is False
    assert r["error"] == "Thiếu ký tự/từ"


def test_separator_with_nothing_after_it_is_invalid():
    r = parse_line("猫 - ")
    assert r["character"] == "猫"
    assert r["meaning_vi"] == ""
    assert r["valid"] is False
    assert r["error"] == "Thiếu nghĩa tiếng Việt"


# ── parse_quick_add_text: multi-line input ──────────────────────────────────

def test_parse_multiple_lines():
    text = "猫 - con mèo\n犬: con chó\n食べる\tăn"
    rows = parse_quick_add_text(text)
    assert len(rows) == 3
    assert all(r["valid"] for r in rows)
    assert [r["character"] for r in rows] == ["猫", "犬", "食べる"]


def test_parse_skips_blank_lines_between_groups():
    text = "猫 - con mèo\n\n\n犬 - con chó"
    rows = parse_quick_add_text(text)
    assert len(rows) == 2  # blank lines skipped, not reported as errors
    assert all(r["valid"] for r in rows)


def test_parse_mixed_valid_and_invalid_lines():
    text = "猫 - con mèo\n鳥\n魚 - con cá"
    rows = parse_quick_add_text(text)
    assert len(rows) == 3
    assert rows[0]["valid"] is True
    assert rows[1]["valid"] is False   # "鳥" alone, no meaning
    assert rows[2]["valid"] is True


def test_parse_empty_text_returns_empty_list():
    assert parse_quick_add_text("") == []
    assert parse_quick_add_text(None) == []


def test_parse_preserves_raw_line_for_display():
    rows = parse_quick_add_text("  猫 - con mèo  ")
    assert rows[0]["raw"] == "  猫 - con mèo  "
