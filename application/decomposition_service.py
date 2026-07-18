"""
application/decomposition_service.py — use case: break a kanji down into
its component parts, recursively — e.g. 暗 → 日 + 音, and since 音 is
itself decomposable, 音 → 立 + 日.

Two sources feed this, checked in order per character:
  1. UserDecompositionRepository — parts the person typed in themselves
     (ui/kanji_decomposition_dialog.py's "✏️ Sửa" button). Always wins
     when present, for that character specifically.
  2. KanjiIdsRepository — the bundled offline IDS dataset, used as the
     fallback when there's no user override.
Both are interfaces (domain.repositories); concrete implementations
(infrastructure.kanji_ids.FileKanjiIdsRepository,
infrastructure.db.sqlite_repositories.SqliteUserDecompositionRepository)
are handed in via the constructor by whatever composes the app — same DI
pattern as CardService/DeckService/etc.
"""
from domain.repositories import KanjiIdsRepository, UserDecompositionRepository
from domain.kanji_decomposition import DecompositionNode, IdsParseError, parse_ids

DEFAULT_MAX_DEPTH = 6


class DecompositionService:
    def __init__(self, kanji_ids: KanjiIdsRepository, user_overrides: UserDecompositionRepository = None):
        self._kanji_ids = kanji_ids
        self._user_overrides = user_overrides

    def decompose(self, character: str, max_depth: int = DEFAULT_MAX_DEPTH) -> DecompositionNode:
        """Full recursive breakdown tree for `character`.

        If `character` has no IDS record and no user override, or its
        record just points back to itself (CHISE's convention for
        "atomic, no further breakdown"), the returned node is a childless
        leaf — callers should treat that as "no decomposition available"
        rather than an error. `max_depth` and a per-branch visited-set
        guard against runaway/circular data.
        """
        return self._build(character, depth=0, max_depth=max_depth, visited=frozenset())

    # ── manual overrides (the "✏️ Sửa" feature) ─────────────────────────────

    def get_override(self, character: str) -> str | None:
        """Raw parts string the user has defined for `character` (each
        character in the string is one component), or None if they
        haven't overridden it — meaning it currently falls back to the
        bundled dataset."""
        if not self._user_overrides:
            return None
        return self._user_overrides.get_parts(character)

    def set_override(self, character: str, parts: str) -> None:
        """Replace `character`'s breakdown with exactly these parts (each
        character in `parts` is one component), overriding the bundled
        dataset for it from now on."""
        if self._user_overrides:
            self._user_overrides.set_parts(character, parts)

    def clear_override(self, character: str) -> None:
        """Drop the user's override for `character`, reverting to the
        bundled dataset (or "no data" if it has none either)."""
        if self._user_overrides:
            self._user_overrides.delete(character)

    # ── internals ────────────────────────────────────────────────────────

    def _build(self, character: str, depth: int, max_depth: int,
               visited: frozenset) -> DecompositionNode:
        """Look up `character`'s own breakdown (user override first, else
        the bundled IDS record) and parse it into a tree whose root
        represents `character` itself."""
        if depth >= max_depth or character in visited:
            return DecompositionNode(character=character)

        override_parts = self._user_overrides.get_parts(character) if self._user_overrides else None
        if override_parts is not None:
            children = [DecompositionNode(character=p) for p in override_parts if p != character]
            if not children:
                return DecompositionNode(character=character)
            tree = DecompositionNode(character=character, children=children)
        else:
            ids_str = self._kanji_ids.get_ids(character)
            if not ids_str or ids_str == character:
                return DecompositionNode(character=character)
            try:
                tree = parse_ids(ids_str)
            except IdsParseError:
                return DecompositionNode(character=character)
            tree.character = character

        next_visited = visited | {character}
        tree.children = [
            self._expand(child, depth + 1, max_depth, next_visited)
            for child in tree.children
        ]
        return tree

    def _expand(self, node: DecompositionNode, depth: int, max_depth: int,
                visited: frozenset) -> DecompositionNode:
        """Expand one node from within a just-parsed breakdown. If it's
        already a group (a nested IDC within the same bundled IDS entry,
        e.g. the "⿻了叹" part of 亟's "⿱⿻了叹一"), recurse into its own
        children. If it's a plain leaf character, treat it as a new
        character and look up *its* own breakdown (this is the
        cross-entry recursion: 音 inside 暗's tree gets expanded via its
        own record, user override or bundled)."""
        if node.children:
            node.children = [
                self._expand(child, depth, max_depth, visited)
                for child in node.children
            ]
            return node
        return self._build(node.character, depth, max_depth, visited)
