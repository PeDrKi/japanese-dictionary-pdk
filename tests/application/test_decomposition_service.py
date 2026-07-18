"""
Tests for application/decomposition_service.py.

Uses a plain dict-backed fake instead of the real file-based repository
(infrastructure.kanji_ids.FileKanjiIdsRepository) — any object with a
matching get_ids() satisfies the KanjiIdsRepository Protocol, per the
structural-typing rationale in domain/repositories.py.
"""
from application.decomposition_service import DecompositionService


class FakeKanjiIdsRepository:
    def __init__(self, data: dict):
        self._data = data

    def get_ids(self, character: str):
        return self._data.get(character)


class FakeUserDecompositionRepository:
    def __init__(self, data: dict = None):
        self._data = dict(data or {})

    def get_parts(self, character: str):
        return self._data.get(character)

    def set_parts(self, character: str, parts: str):
        self._data[character] = parts

    def delete(self, character: str):
        self._data.pop(character, None)

    def get_all(self):
        return [{"character": c, "parts": p} for c, p in self._data.items()]


def make_service(data: dict, overrides: dict = None) -> DecompositionService:
    return DecompositionService(FakeKanjiIdsRepository(data), FakeUserDecompositionRepository(overrides))


# ── the example from the user's own request ─────────────────────────────────

def test_decomposes_and_recurses_into_a_further_decomposable_child():
    # 暗 = 日 + 音, and 音 itself = 立 + 日
    service = make_service({
        "暗": "⿰日音",
        "音": "⿱立日",
        "日": "日",   # atomic — CHISE convention for "no further breakdown"
        "立": "立",
    })

    tree = service.decompose("暗")

    assert tree.character == "暗"
    assert tree.operator == "⿰"
    day, oto = tree.children
    assert day.character == "日"
    assert day.is_leaf  # 日 has no further breakdown on record

    assert oto.character == "音"
    assert oto.operator == "⿱"  # 音 got expanded, not left as a bare leaf
    ritsu, day2 = oto.children
    assert ritsu.character == "立"
    assert ritsu.is_leaf
    assert day2.character == "日"
    assert day2.is_leaf


# ── edge cases ───────────────────────────────────────────────────────────────

def test_character_with_no_record_returns_childless_leaf():
    service = make_service({})
    tree = service.decompose("暗")
    assert tree.character == "暗"
    assert tree.is_leaf


def test_max_depth_stops_further_recursion():
    service = make_service({
        "暗": "⿰日音",
        "音": "⿱立日",
        "立": "立",
    })
    tree = service.decompose("暗", max_depth=1)
    oto = tree.children[1]
    assert oto.character == "音"
    assert oto.is_leaf  # would normally expand into 立/日, but depth cap stops it


def test_cyclical_data_does_not_infinite_loop():
    # Pathological data: A decomposes into B, B decomposes into A.
    service = make_service({
        "A": "⿰AB",
        "B": "⿰BA",
    })
    tree = service.decompose("A", max_depth=10)  # must return, not hang
    assert tree.character == "A"


# ── user overrides ("tự nhập/thêm mới hoàn toàn cách tách bộ") ──────────────

def test_user_override_wins_over_bundled_data():
    service = make_service(
        data={"暗": "⿰日音"},              # bundled says 暗 = 日 + 音
        overrides={"暗": "日寺"},           # user says otherwise
    )
    tree = service.decompose("暗")
    assert [c.character for c in tree.children] == ["日", "寺"]


def test_user_override_supplies_a_character_with_no_bundled_data():
    service = make_service(data={}, overrides={"㐀": "一乙"})
    tree = service.decompose("㐀")
    assert [c.character for c in tree.children] == ["一", "乙"]


def test_overridden_child_is_itself_further_decomposable():
    # 暗's own breakdown is untouched (bundled), but the user has
    # separately overridden what 音 (one of its parts) breaks down into.
    service = make_service(
        data={"暗": "⿰日音", "音": "⿱立日"},
        overrides={"音": "亠日"},
    )
    tree = service.decompose("暗")
    _, oto = tree.children
    assert oto.character == "音"
    assert [c.character for c in oto.children] == ["亠", "日"]


def test_set_and_clear_override_round_trip():
    service = make_service(data={"暗": "⿰日音"})
    assert service.get_override("暗") is None

    service.set_override("暗", "日寺")
    assert service.get_override("暗") == "日寺"
    assert [c.character for c in service.decompose("暗").children] == ["日", "寺"]

    service.clear_override("暗")
    assert service.get_override("暗") is None
    assert [c.character for c in service.decompose("暗").children] == ["日", "音"]


def test_service_works_without_a_user_overrides_repository():
    # user_overrides is optional — DecompositionService(kanji_ids_only) must
    # still behave exactly as before overrides existed.
    service = DecompositionService(FakeKanjiIdsRepository({"暗": "⿰日音"}))
    assert service.get_override("暗") is None
    service.set_override("暗", "日寺")  # no-op, must not raise
    tree = service.decompose("暗")
    assert [c.character for c in tree.children] == ["日", "音"]


def test_explicitly_empty_override_means_no_data_not_fallback():
    # Saving an empty override is how the "✏️ Sửa" dialog lets someone say
    # "no, this character really has no breakdown" — it must NOT silently
    # fall back to the bundled data (that's different from never having
    # set an override at all).
    service = make_service(data={"暗": "⿰日音"}, overrides={"暗": ""})
    tree = service.decompose("暗")
    assert tree.is_leaf
    assert service.get_override("暗") == ""  # distinguishable from None
