"""
infrastructure/kanji_ids.py — offline IDS (Ideographic Description
Sequence) lookup, backing the kanji-decomposition feature.

Data: infrastructure/data/kanji_ids.tsv, derived from the CHISE IDS
Database via the cjkvi/cjkvi-ids project, filtered to CJK Unified
Ideographs + Extension A. See infrastructure/data/README.md for
provenance and license.

No network access, no database — a flat file loaded once into memory
and cached at module level, the same spirit as infrastructure/settings.py.
"""
import os
from typing import Optional

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "kanji_ids.tsv")
_cache: Optional[dict] = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    data: dict = {}
    try:
        with open(_DATA_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                char, _, ids_str = line.partition("\t")
                if char and ids_str:
                    data[char] = ids_str
    except FileNotFoundError:
        data = {}
    _cache = data
    return data


def get_ids(character: str) -> Optional[str]:
    """Raw IDS string for `character` (e.g. "暗" -> "⿰日音"), or None if
    there's no record for it."""
    return _load().get(character)


class FileKanjiIdsRepository:
    """Satisfies domain.repositories.KanjiIdsRepository."""

    def get_ids(self, character: str) -> Optional[str]:
        return get_ids(character)
