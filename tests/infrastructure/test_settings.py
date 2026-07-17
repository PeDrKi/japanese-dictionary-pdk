"""
Tests for utils/settings.py — persistent settings load/save,
including the fallback behavior when the file is missing or corrupted.
"""
import json
import importlib

from infrastructure import settings as settings_module


def _reload_with_path(monkeypatch, path):
    """Point the settings module at `path` and clear its in-memory cache."""
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", str(path))
    monkeypatch.setattr(settings_module, "_cache", {})
    return settings_module


def test_load_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    mod = _reload_with_path(monkeypatch, tmp_path / "does_not_exist.json")
    data = mod.load()
    assert data["theme"] == "dark"
    assert data["page_size"] == 20


def test_load_returns_defaults_when_file_corrupted(tmp_path, monkeypatch, caplog):
    bad_file = tmp_path / "settings.json"
    bad_file.write_text("{ this is not valid json ]", encoding="utf-8")
    mod = _reload_with_path(monkeypatch, bad_file)
    with caplog.at_level("WARNING"):
        data = mod.load()
    assert data["theme"] == "dark"  # falls back to defaults, doesn't crash
    assert any("Could not load settings" in r.message for r in caplog.records)


def test_load_merges_saved_values_over_defaults(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"theme": "light", "page_size": 50}), encoding="utf-8")
    mod = _reload_with_path(monkeypatch, f)
    data = mod.load()
    assert data["theme"] == "light"
    assert data["page_size"] == 50
    assert data["last_tab"] == "table"  # untouched default still present


def test_set_persists_value_to_disk(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    mod = _reload_with_path(monkeypatch, f)
    mod.set("theme", "light")
    assert mod.get("theme") == "light"
    # Confirm it actually hit disk, not just the in-memory cache.
    on_disk = json.loads(f.read_text(encoding="utf-8"))
    assert on_disk["theme"] == "light"


def test_update_merges_multiple_keys(tmp_path, monkeypatch):
    f = tmp_path / "settings.json"
    mod = _reload_with_path(monkeypatch, f)
    mod.update({"theme": "light", "page_size": 10})
    assert mod.get("theme") == "light"
    assert mod.get("page_size") == 10


def test_get_returns_default_for_unknown_key(tmp_path, monkeypatch):
    mod = _reload_with_path(monkeypatch, tmp_path / "settings.json")
    assert mod.get("no_such_key", "fallback") == "fallback"
