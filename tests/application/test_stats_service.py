import pytest

from application.stats_service import StatsService
from infrastructure.db.sqlite_repositories import SqliteStatsRepository
from database import models


@pytest.fixture
def service(fresh_db):
    return StatsService(SqliteStatsRepository())


def test_get_summary_matches_models(service):
    assert service.get_summary() == models.get_stats()


def test_get_full_matches_models(service):
    assert service.get_full() == models.get_full_stats()


def test_get_summary_shape(service):
    summary = service.get_summary()
    assert set(summary.keys()) == {"total", "by_type", "by_status", "favorites"}
    assert summary["total"] == 17  # sample data seeds 17 cards
