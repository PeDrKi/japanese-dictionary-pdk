"""
Tests for utils/media.py — cross-platform "open with default app" helper.
"""
import sys
import subprocess

from infrastructure.media import open_with_default_app


def test_missing_path_returns_error():
    ok, msg = open_with_default_app("")
    assert ok is False
    assert "Chưa chọn" in msg


def test_nonexistent_file_returns_error(tmp_path):
    ok, msg = open_with_default_app(str(tmp_path / "no_such_file.mp3"))
    assert ok is False
    assert "không tồn tại" in msg


def test_existing_file_dispatches_to_platform_opener(tmp_path, monkeypatch):
    f = tmp_path / "sound.mp3"
    f.write_bytes(b"fake audio data")

    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run",
                         lambda args, **kw: calls.append(args) or None)

    ok, msg = open_with_default_app(str(f))
    assert ok is True
    assert calls == [["xdg-open", str(f)]]


def test_subprocess_failure_is_reported_not_raised(tmp_path, monkeypatch):
    f = tmp_path / "sound.mp3"
    f.write_bytes(b"fake audio data")

    def _raise(*a, **kw):
        raise OSError("no player installed")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", _raise)

    ok, msg = open_with_default_app(str(f))
    assert ok is False
    assert "Không thể mở file" in msg
