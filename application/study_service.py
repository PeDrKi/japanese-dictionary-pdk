"""
application/study_service.py — use case for recording a quiz/flashcard
answer.

Kept intentionally thin: a single log_study(card_id, result) call,
matching database.models.log_study's exact signature and behavior
today. The actual SRS math and status state machine already live in
domain/srs.py (Stage 1) and are applied inside the SqliteStudySessionRepository
→ database/_study.py chain — this service does not duplicate that logic,
it just gives ui/ a single, stable place to call instead of importing
database.models directly.

A "richer" version of this service — read the Card, ask domain.srs what
changes, write it back through CardRepository, record the attempt
through StudySessionRepository separately — is described in the refactor
plan (section 3.2) as the fuller Clean Architecture shape. It's not done
here because it requires a real Card entity to pass between layers,
which the plan explicitly marks as optional (section 5) rather than
required for this boundary to be useful.
"""
from domain.repositories import StudySessionRepository


class StudyService:
    def __init__(self, sessions: StudySessionRepository):
        self._sessions = sessions

    def log_study(self, card_id: int, result: str) -> None:
        self._sessions.log(card_id, result)
