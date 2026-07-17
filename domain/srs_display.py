"""
domain/srs_display.py — pure helpers for presenting SRS scheduling info to
the user (e.g. in ui/card_detail.py: "🎯 Cần ôn ngay" / "Còn 5 ngày nữa").
Moved from utils/ (Stage: utils/ cleanup).

Kept separate from database/_study.py (which computes the *next* schedule)
because this is purely about *displaying* an already-stored schedule —
no DB access, easy to unit test with fixed dates.
"""
from datetime import date, datetime


def format_due_info(srs_due_date, today: date = None) -> str:
    """
    Human-friendly Vietnamese description of when a card is next due.

    `srs_due_date` — a "YYYY-MM-DD" string (or None for a never-studied
    card, which is always due immediately).
    `today` — injectable for testing; defaults to date.today().
    """
    today = today or date.today()

    if not srs_due_date:
        return "🆕 Thẻ mới — cần ôn ngay"

    try:
        due = datetime.strptime(srs_due_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return "🆕 Cần ôn ngay"

    days_left = (due - today).days
    if days_left <= 0:
        return "🎯 Cần ôn ngay"
    if days_left == 1:
        return f"⏳ Còn 1 ngày nữa ({due.strftime('%d/%m/%Y')})"
    return f"⏳ Còn {days_left} ngày nữa ({due.strftime('%d/%m/%Y')})"


def format_ease_label(srs_ease) -> str:
    """
    Turn the raw ease-factor number into a rough, non-technical Vietnamese
    label — most users don't need to know "2.6", just "thẻ này khá dễ".
    """
    if srs_ease is None:
        return "—"
    if srs_ease <= 1.6:
        return "🔴 Khó — cần ôn thường xuyên"
    if srs_ease <= 2.2:
        return "🟡 Trung bình"
    return "🟢 Dễ — giãn cách ôn dài"
