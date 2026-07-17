"""
domain/srs.py — Spaced-repetition scheduling rules (simplified SM-2) and
the card status state machine. Pure business logic: no sqlite3, no I/O,
no import from database/ or ui/.

Moved here (Stage 1 of the clean-architecture migration) from
database/_study.py, where the scheduling math (compute_srs_update) already
lived as a standalone pure function, and from an inline SQL CASE
expression inside log_study(), which encoded the status state machine as
a string of SQL rather than as a rule you could read or test directly.

database/_study.py now imports from here and re-exports the same names
(_compute_srs_update, SRS_*) so database.models's public API — and every
existing test that calls it — is unaffected.
"""

# SRS tuning — simplified SM-2 with a binary (correct/incorrect) signal
# instead of SM-2's usual 0-5 quality rating:
#   - correct:   ease nudges up (card is "easy") and the interval grows by
#                that ease multiplier, so consistently-easy cards get spaced
#                out faster than a flat doubling would.
#   - incorrect: ease drops (card is "hard") and interval resets to 1 day,
#                so a card that's proving difficult comes back sooner next
#                time even after it builds up a long interval.
SRS_MAX_INTERVAL_DAYS = 90
SRS_MIN_EASE = 1.3
SRS_MAX_EASE = 2.8
SRS_EASE_STEP = 0.1        # nudge on correct
SRS_EASE_PENALTY = 0.2     # nudge on incorrect
SRS_DEFAULT_EASE = 2.5


def compute_srs_update(current_interval: int, current_ease: float, result: str):
    """
    Pure SRS scheduling function (no DB access) — the algorithm itself,
    unit tested directly without needing a database.
    Returns (new_interval: int, new_ease: float).
    """
    current_interval = current_interval or 1
    current_ease = current_ease or SRS_DEFAULT_EASE

    if result == 'correct':
        new_ease = min(current_ease + SRS_EASE_STEP, SRS_MAX_EASE)
        # Guarantee the interval always grows on a correct answer, even
        # when interval*ease rounds down to the same value (e.g. 1*1.3).
        grown = round(current_interval * new_ease)
        new_interval = min(max(current_interval + 1, grown), SRS_MAX_INTERVAL_DAYS)
    else:
        new_ease = max(current_ease - SRS_EASE_PENALTY, SRS_MIN_EASE)
        new_interval = 1

    return new_interval, new_ease


def next_status(current_status: str, result: str) -> str:
    """
    Card status state machine:
        new      --correct--> learning
        learning --correct--> known
        known    --correct--> known      (stays)
        known    --incorrect--> learning
        anything else --incorrect--> new

    Extracted from the SQL CASE expression that used to live inline in
    database/_study.py's log_study(), so the rule can be read and tested
    on its own instead of only being exercisable by running a real query.
    """
    if result == 'correct':
        if current_status == 'new':
            return 'learning'
        return 'known'  # learning -> known, known -> known
    else:
        if current_status == 'known':
            return 'learning'
        return 'new'  # learning -> new, new -> new
