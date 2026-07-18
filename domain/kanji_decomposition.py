"""
domain/kanji_decomposition.py — parsing for IDS (Ideographic Description
Sequence) strings, e.g. "⿰日音" (日 next to 音, left-right) or
"⿱立日" (立 above 日).

This module only parses ONE IDS string into a tree — it has no notion of
"look up this character's own IDS and recurse into it too" (that needs a
data source, so it belongs in application/decomposition_service.py,
which calls parse_ids() once per character it looks up). Nothing outside
domain/ is imported here, same rule as domain/repositories.py.

An IDC (Ideographic Description Character, U+2FF0–U+2FFB) combines 2 or
3 operands — e.g. "⿰日音" is IDC ⿰ combining 日 and 音. IDS strings can
already nest several IDCs in one entry, e.g. 亟's IDS is "⿱⿻了叹一"
(⿱ combining (⿻ combining 了 and 叹) and 一) — parse_ids() walks that
nesting directly via recursive descent.
"""
from dataclasses import dataclass, field
from typing import Optional


class IdsParseError(ValueError):
    """Raised when a string isn't a well-formed IDS (Ideographic
    Description Sequence)."""


# Arity (operand count) of each standard IDC. All are 2 except the
# three-way left-middle-right / top-middle-bottom operators.
IDC_ARITY = {
    "⿰": 2, "⿱": 2, "⿲": 3, "⿳": 3, "⿴": 2, "⿵": 2,
    "⿶": 2, "⿷": 2, "⿸": 2, "⿹": 2, "⿺": 2, "⿻": 2,
}

# Vietnamese label for each IDC, for display purposes.
IDC_LABELS = {
    "⿰": "trái – phải",
    "⿱": "trên – dưới",
    "⿲": "trái – giữa – phải",
    "⿳": "trên – giữa – dưới",
    "⿴": "bao quanh (kín)",
    "⿵": "bao phía trên",
    "⿶": "bao phía dưới",
    "⿷": "bao phía trái",
    "⿸": "bao góc trên-trái",
    "⿹": "bao góc trên-phải",
    "⿺": "bao góc dưới-trái",
    "⿻": "chồng lên nhau",
}


@dataclass
class DecompositionNode:
    """One node in a decomposition tree.

    - Leaf (no further breakdown known): operator is None, children is [].
    - Composite: operator is the IDC combining `children` (2 or 3 of them).

    `character` is the glyph this node stands for. For nodes produced
    purely by parse_ids() from a nested IDC (a grouping that has no
    dictionary character of its own, e.g. the "⿻了叹" sub-group inside
    亟's IDS), it's left as an empty string — application code that knows
    the real character (the one being decomposed) fills this in.
    """
    character: str = ""
    operator: Optional[str] = None
    children: list["DecompositionNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children


def parse_ids(ids_string: str) -> DecompositionNode:
    """Parse one IDS string (e.g. "⿰日音") into a DecompositionNode tree.

    Raises IdsParseError if the string is empty, malformed, or has
    trailing characters left over after a complete parse.
    """
    ids_string = (ids_string or "").strip()
    if not ids_string:
        raise IdsParseError("Chuỗi IDS rỗng")

    pos = 0

    def parse_unit() -> DecompositionNode:
        nonlocal pos
        if pos >= len(ids_string):
            raise IdsParseError(f"Chuỗi IDS không hợp lệ: {ids_string!r}")
        ch = ids_string[pos]
        pos += 1
        arity = IDC_ARITY.get(ch)
        if arity is None:
            # A plain character — leaf of this (sub-)tree.
            return DecompositionNode(character=ch)
        children = [parse_unit() for _ in range(arity)]
        return DecompositionNode(operator=ch, children=children)

    root = parse_unit()
    if pos != len(ids_string):
        raise IdsParseError(f"Dư ký tự sau khi phân tích IDS: {ids_string!r}")
    return root
