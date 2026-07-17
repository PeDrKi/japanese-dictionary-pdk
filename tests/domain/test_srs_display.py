"""
Tests for utils/srs_display.py — pure formatting helpers, no DB/GUI.
"""
from datetime import date

from domain.srs_display import format_due_info, format_ease_label


FIXED_TODAY = date(2026, 7, 4)


def test_none_due_date_means_new_card():
    assert "Thẻ mới" in format_due_info(None, today=FIXED_TODAY)


def test_due_date_today_means_due_now():
    assert format_due_info("2026-07-04", today=FIXED_TODAY) == "🎯 Cần ôn ngay"


def test_due_date_in_past_means_overdue_but_still_due_now():
    assert format_due_info("2026-06-01", today=FIXED_TODAY) == "🎯 Cần ôn ngay"


def test_due_date_tomorrow_uses_singular_day_wording():
    result = format_due_info("2026-07-05", today=FIXED_TODAY)
    assert "1 ngày nữa" in result
    assert "05/07/2026" in result


def test_due_date_several_days_out():
    result = format_due_info("2026-07-10", today=FIXED_TODAY)
    assert "6 ngày nữa" in result


def test_malformed_date_string_falls_back_gracefully():
    result = format_due_info("not-a-date", today=FIXED_TODAY)
    assert "Cần ôn ngay" in result


def test_ease_label_low_is_hard():
    assert "Khó" in format_ease_label(1.3)


def test_ease_label_mid_is_average():
    assert "Trung bình" in format_ease_label(2.0)


def test_ease_label_high_is_easy():
    assert "Dễ" in format_ease_label(2.7)


def test_ease_label_none_is_placeholder():
    assert format_ease_label(None) == "—"


def test_ease_label_boundaries_are_consistent_with_srs_default():
    """The SRS default ease (2.5, from database/_study.py) should land in
    the 'easy' band — a brand-new card hasn't been studied yet, but this
    guards against the label bands drifting out of sync with SRS_DEFAULT_EASE
    if either changes independently."""
    from database.models import SRS_DEFAULT_EASE
    assert "Dễ" in format_ease_label(SRS_DEFAULT_EASE)
