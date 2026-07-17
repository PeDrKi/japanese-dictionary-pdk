import pytest

from application.card_service import CardService
from application.study_service import StudyService
from infrastructure.db.sqlite_repositories import (
    SqliteCardRepository,
    SqliteStudySessionRepository,
)
from tests.conftest import card_payload


@pytest.fixture
def services(fresh_db):
    cards = CardService(SqliteCardRepository())
    study = StudyService(SqliteStudySessionRepository())
    return cards, study


def test_log_study_correct_updates_card(services):
    cards, study = services
    card_id = cards.add(card_payload(status="new"))

    study.log_study(card_id, "correct")

    card = cards.get(card_id)
    assert card["status"] == "learning"
    assert card["srs_interval"] > 1


def test_log_study_incorrect_resets_interval(services):
    cards, study = services
    card_id = cards.add(card_payload(status="known"))

    # Grow the interval past 1 first (srs_interval isn't settable via
    # add_card — it's a schema default — so we get there the same way
    # the real app would: by answering correctly a few times).
    study.log_study(card_id, "correct")
    study.log_study(card_id, "correct")
    assert cards.get(card_id)["srs_interval"] > 1

    study.log_study(card_id, "incorrect")

    card = cards.get(card_id)
    assert card["status"] == "learning"
    assert card["srs_interval"] == 1
