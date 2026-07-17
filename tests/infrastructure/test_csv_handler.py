"""
Tests for utils/csv_handler.py — CSV import/export.
"""
import csv

from infrastructure.csv_handler import import_csv, export_csv, FIELDS


def _write_csv(tmp_path, content, name="cards.csv"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8-sig")
    return str(p)


def test_import_valid_row(tmp_path):
    path = _write_csv(tmp_path, "type,character,meaning_vi\nvocab,犬,con chó\n")
    valid, errors = import_csv(path)
    assert errors == []
    assert len(valid) == 1
    assert valid[0]["character"] == "犬"
    assert valid[0]["meaning_vi"] == "con chó"


def test_import_missing_file_returns_error():
    valid, errors = import_csv("/no/such/file.csv")
    assert valid == []
    assert errors and errors[0][1] == "File không tồn tại"


def test_import_row_missing_required_field_reports_error_not_crash(tmp_path):
    path = _write_csv(tmp_path, "type,character,meaning_vi\nvocab,,con chó\n")
    valid, errors = import_csv(path)
    assert valid == []
    assert errors[0][1] == "Thiếu 'character'"


def test_import_invalid_type_reports_error(tmp_path):
    path = _write_csv(tmp_path, "type,character,meaning_vi\nfoo,犬,con chó\n")
    valid, errors = import_csv(path)
    assert valid == []
    assert "type không hợp lệ" in errors[0][1]


def test_import_short_row_does_not_crash_whole_file(tmp_path):
    """Regression test: a short/malformed row used to raise AttributeError
    (None.strip()) and abort the entire import. It must now just be
    reported as a per-row error while later valid rows still import."""
    content = "type,character,meaning_vi,reading_kana\nvocab,犬\nvocab,猫,con mèo,ねこ\n"
    path = _write_csv(tmp_path, content)
    valid, errors = import_csv(path)
    assert len(valid) == 1
    assert valid[0]["character"] == "猫"
    assert len(errors) == 1
    assert errors[0][1] == "Thiếu 'meaning_vi'"


def test_import_blank_optional_fields_become_none(tmp_path):
    path = _write_csv(tmp_path, "type,character,meaning_vi,romaji\nvocab,犬,con chó,\n")
    valid, _ = import_csv(path)
    assert valid[0]["romaji"] is None


def test_import_stroke_count_non_numeric_becomes_none(tmp_path):
    path = _write_csv(tmp_path, "type,character,meaning_vi,stroke_count\nkanji,雨,mưa,abc\n")
    valid, _ = import_csv(path)
    assert valid[0]["stroke_count"] is None


def test_import_stroke_count_numeric_parsed(tmp_path):
    path = _write_csv(tmp_path, "type,character,meaning_vi,stroke_count\nkanji,雨,mưa,8\n")
    valid, _ = import_csv(path)
    assert valid[0]["stroke_count"] == 8


def test_import_normalizes_multiple_readings(tmp_path):
    """Multiple on/kun readings typed with an ASCII comma or slash in the
    CSV should be normalized to the app's "、" separator, same as when
    typed directly into the Add/Edit card form (utils/validators.py)."""
    content = ("type,character,meaning_vi,reading_on,reading_kun\n"
               "kanji,月,mặt trăng,\"getsu, gatsu\",tsuki\n")
    path = _write_csv(tmp_path, content)
    valid, errors = import_csv(path)
    assert errors == []
    assert valid[0]["reading_on"] == "getsu、gatsu"
    assert valid[0]["reading_kun"] == "tsuki"


def test_export_then_import_roundtrip(tmp_path):
    cards = [{
        "type": "vocab", "character": "犬", "reading_on": None, "reading_kun": None,
        "reading_kana": "いぬ", "romaji": "inu", "meaning_vi": "con chó",
        "meaning_en": "dog", "example_jp": None, "example_vi": None,
        "stroke_count": None, "jlpt_level": "N5", "status": "new",
        "is_favorite": 0, "source": "test", "notes": None,
    }]
    path = str(tmp_path / "export.csv")
    n = export_csv(cards, path)
    assert n == 1

    valid, errors = import_csv(path)
    assert errors == []
    assert valid[0]["character"] == "犬"
    assert valid[0]["meaning_vi"] == "con chó"
