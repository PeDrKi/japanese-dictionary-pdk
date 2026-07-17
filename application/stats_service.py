"""
application/stats_service.py — dashboard statistics use cases.

Thin pass-through to domain.repositories.StatsRepository. Both methods
are read-only aggregate queries with no business rule beyond what SQL
already computes (see database/_stats.py) — the service exists for the
same reason DeckService does: one consistent boundary (application.*)
for ui/ to depend on across every feature area.
"""
from domain.repositories import StatsRepository


class StatsService:
    def __init__(self, stats: StatsRepository):
        self._stats = stats

    def get_summary(self) -> dict:
        return self._stats.get_summary()

    def get_full(self) -> dict:
        return self._stats.get_full()
