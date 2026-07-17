"""
infrastructure/db/sqlite_repositories.py — SQLite implementations of the
repository interfaces declared in domain/repositories.py.

Stage 2 of the clean-architecture migration: these classes are thin
wrappers around the already-working functions in database/_cards.py,
database/_decks.py, database/_study.py (via the database.models public
facade) — no SQL is rewritten here, no behavior changes. Their only job
is to give the rest of the app (future application/ services, and
eventually ui/) an interface to depend on instead of importing
`database.models` directly.

Each class takes no constructor arguments today because database.models
manages its own thread-local connection internally (see
database/_common.py) — there's no connection object to inject yet. That
plumbing can move here in a later stage if/when the connection lifecycle
itself needs to become swappable (e.g. for a from-scratch test double
that doesn't touch SQLite at all); until then these classes exist purely
to satisfy the Protocol shape so callers can depend on
domain.repositories.CardRepository etc. instead of a concrete module.
"""
from database import models


class SqliteCardRepository:
    """Implements domain.repositories.CardRepository."""

    def get_all(self, *, type_filter=None, jlpt_filter=None, status_filter=None,
                favorite_only=False, deck_id=None, search=None,
                include_deleted=False, due_only=False, limit=None, offset=0):
        return models.get_all_cards(
            type_filter=type_filter, jlpt_filter=jlpt_filter,
            status_filter=status_filter, favorite_only=favorite_only,
            deck_id=deck_id, search=search, include_deleted=include_deleted,
            due_only=due_only, limit=limit, offset=offset,
        )

    def count(self, *, type_filter=None, jlpt_filter=None, status_filter=None,
              favorite_only=False, deck_id=None, search=None, due_only=False):
        return models.count_cards(
            type_filter=type_filter, jlpt_filter=jlpt_filter,
            status_filter=status_filter, favorite_only=favorite_only,
            deck_id=deck_id, search=search, due_only=due_only,
        )

    def get_due_count(self):
        return models.get_due_count()

    def get_by_id(self, card_id):
        return models.get_card_by_id(card_id)

    def add(self, data):
        return models.add_card(data)

    def update(self, card_id, data):
        models.update_card(card_id, data)

    def soft_delete(self, card_id):
        return models.soft_delete_card(card_id)

    def restore(self, card_id):
        models.restore_card(card_id)

    def hard_delete(self, card_id):
        models.hard_delete_card(card_id)

    def get_deleted(self):
        return models.get_deleted_cards()

    def toggle_favorite(self, card_id):
        models.toggle_favorite(card_id)

    def find_duplicates(self, character, card_type, exclude_id=None):
        return models.find_duplicates(character, card_type, exclude_id=exclude_id)

    def bulk_update_status(self, ids, status):
        models.bulk_update_status(ids, status)

    def bulk_toggle_favorite(self, ids):
        models.bulk_toggle_favorite(ids)

    def bulk_soft_delete(self, ids):
        return models.bulk_soft_delete(ids)


class SqliteDeckRepository:
    """Implements domain.repositories.DeckRepository."""

    def get_all(self):
        return models.get_all_decks()

    def add(self, name, description="", color="#4A90D9", icon="📁", category_id=None):
        return models.add_deck(name, description, color, icon, category_id)

    def update(self, deck_id, name, description, color, icon, category_id=None):
        models.update_deck(deck_id, name, description, color, icon, category_id)

    def delete(self, deck_id):
        models.delete_deck(deck_id)

    def add_card(self, deck_id, card_id):
        models.add_card_to_deck(deck_id, card_id)

    def remove_card(self, deck_id, card_id):
        models.remove_card_from_deck(deck_id, card_id)

    def bulk_add_cards(self, deck_id, ids):
        models.bulk_add_to_deck(deck_id, ids)

    def get_all_categories(self):
        return models.get_all_categories()

    def add_category(self, name, icon="🗂️"):
        return models.add_category(name, icon)

    def update_category(self, category_id, name, icon):
        models.update_category(category_id, name, icon)

    def delete_category(self, category_id):
        models.delete_category(category_id)

    def get_decks_for_card(self, card_id):
        return models.get_decks_for_card(card_id)


class SqliteStudySessionRepository:
    """Implements domain.repositories.StudySessionRepository."""

    def log(self, card_id, result):
        models.log_study(card_id, result)


class SqliteStatsRepository:
    """Implements domain.repositories.StatsRepository."""

    def get_summary(self):
        return models.get_stats()

    def get_full(self):
        return models.get_full_stats()
