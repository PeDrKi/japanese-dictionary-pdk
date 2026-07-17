"""
Tests for infrastructure/translate.py — only the parts that don't need a
real network call (cache get/set, empty-input short-circuit). The actual
HTTP call (suggest_vi's _run inner function) isn't covered here, mirroring
this project's existing convention for infrastructure/jisho.py (also
untested for the same reason: no test double for the network call exists
yet in this codebase).
"""
import threading
import time

from infrastructure import translate


def _wait_for(predicate, timeout=2.0):
    """Poll until predicate() is true or timeout — callbacks run on a
    background thread, so tests need to wait for them."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def setup_function(_):
    translate.clear_cache()


def test_suggest_vi_empty_input_returns_none_no_network():
    result = {}
    translate.suggest_vi("", lambda t, e: result.update(translation=t, error=e))
    assert _wait_for(lambda: "translation" in result)
    assert result["translation"] is None
    assert result["error"] is None


def test_suggest_vi_whitespace_only_returns_none():
    result = {}
    translate.suggest_vi("   ", lambda t, e: result.update(translation=t, error=e))
    assert _wait_for(lambda: "translation" in result)
    assert result["translation"] is None


def test_cache_hit_skips_network_call():
    translate._cache_set("rain", "mưa")
    result = {}
    translate.suggest_vi("rain", lambda t, e: result.update(translation=t, error=e))
    assert _wait_for(lambda: "translation" in result)
    assert result["translation"] == "mưa"
    assert result["error"] is None


def test_cache_lookup_is_case_insensitive():
    translate._cache_set("Rain", "mưa")
    assert translate._cache_get("rain") == "mưa"
    assert translate._cache_get("RAIN") == "mưa"


def test_clear_cache_empties_it():
    translate._cache_set("rain", "mưa")
    translate.clear_cache()
    assert translate._cache_get("rain") is None


def test_cache_eviction_at_max_size():
    for i in range(translate._CACHE_MAX + 5):
        translate._cache_set(f"word{i}", f"nghĩa{i}")
    assert len(translate._CACHE) <= translate._CACHE_MAX
