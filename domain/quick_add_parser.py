"""
domain/quick_add_parser.py — parses pasted multi-line text into card rows
for the "⚡ Nhập nhanh" (quick add) dialog (ui/quick_add_dialog.py).

Pure text parsing, no I/O, no customtkinter — one line in, one parsed
row out. Kept separate from the dialog so the parsing rules (which
separators are recognized, how blank/malformed lines are reported) are
unit-testable without opening any widget.
"""
import re

# Accepted separators between character and meaning, tried in this order:
# a tab (pasted from a spreadsheet) or one of - : – — with any amount of
# surrounding whitespace (including none — "猫-con mèo" works same as
# "猫 - con mèo"). maxsplit=1 so a dash appearing later inside the
# meaning itself (e.g. "con chó - giống Nhật") doesn't get split again.
_SEPARATOR_RE = re.compile(r"\t|\s*[-:–—]\s*")


def parse_line(line: str) -> dict:
    """
    Parse one line into:
        {"character": str, "meaning_vi": str, "raw": str,
         "valid": bool, "error": str | None}

    Format: "<character><separator><meaning>". A line with no recognized
    separator is treated as character-only — meaning_vi comes out empty,
    which is flagged invalid since meaning_vi is required on every card
    (same rule domain/validators.validate_required enforces for the
    regular Add Card form).
    """
    raw = line
    line = line.strip()
    if not line:
        return {"character": "", "meaning_vi": "", "raw": raw,
                "valid": False, "error": "Dòng trống"}

    parts = _SEPARATOR_RE.split(line, maxsplit=1)
    character = parts[0].strip()
    meaning_vi = parts[1].strip() if len(parts) > 1 else ""

    if not character:
        return {"character": character, "meaning_vi": meaning_vi, "raw": raw,
                "valid": False, "error": "Thiếu ký tự/từ"}
    if not meaning_vi:
        return {"character": character, "meaning_vi": meaning_vi, "raw": raw,
                "valid": False, "error": "Thiếu nghĩa tiếng Việt"}

    return {"character": character, "meaning_vi": meaning_vi, "raw": raw,
            "valid": True, "error": None}


def parse_quick_add_text(text: str) -> list:
    """
    Parse every non-empty line of pasted text into rows (see parse_line).
    Blank lines are skipped entirely (not reported as errors) so the
    user can paste text with blank-line separation between groups
    without every gap showing up as a "Dòng trống" error.
    """
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        rows.append(parse_line(line))
    return rows
