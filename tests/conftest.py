"""
Shared pytest fixtures for the test suite.

Key idea: every test gets its own throwaway SQLite file (via tmp_path),
so tests never touch the real `database/japanese.db` and can run in
parallel / repeatedly without side effects.
"""
import os
import sys

# Make the project root importable (main.pyw lives here and imports
# `database`, `ui`, `utils`, `constants` as top-level packages).
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from database import db as db_module
from database import models


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """
    Point the app at a brand-new temp SQLite file, initialize the schema
    (+ sample data), and make sure no stale thread-local connection from
    a previous test leaks in. Cleans up its own connection afterwards.
    """
    db_path = tmp_path / "test_japanese.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))

    # Drop any cached connection from a previous test (it would point at
    # the previous test's temp file, not this one).
    models.close_thread_connection()

    db_module.init_db(seed_sample_data=True)

    yield db_path

    models.close_thread_connection()


def card_payload(**overrides):
    """Return a full, valid `cards` row payload for add_card()/update_card(),
    with sane defaults so tests only need to override what they care about."""
    base = dict(
        type="vocab",
        character="犬",
        reading_on=None,
        reading_kun=None,
        reading_kana="いぬ",
        romaji="inu",
        meaning_vi="con chó",
        meaning_en="dog",
        example_jp=None,
        example_vi=None,
        stroke_count=None,
        jlpt_level="N5",
        status="new",
        is_favorite=0,
        source="test",
        notes=None,
        audio_path=None,
        image_path=None,
    )
    base.update(overrides)
    return base
