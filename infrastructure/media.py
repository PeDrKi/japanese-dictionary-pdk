"""
infrastructure/media.py — cross-platform helper for opening a media file
with whatever application the OS has associated with its file type.
Moved from utils/ (Stage: utils/ cleanup) since this shells out to the OS.

Used by ui/card_detail.py's "🔊 Phát âm thanh" button: this app doesn't ship
its own audio player, so playback is delegated to the user's OS default
(e.g. their system's default MP3/WAV player).
"""
import os
import sys
import subprocess


def open_with_default_app(path: str) -> tuple:
    """
    Open `path` with the OS default application for its file type.
    Returns (ok: bool, message: str) — message is a user-facing Vietnamese
    string on failure, or "ok" on success.
    """
    if not path:
        return False, "Chưa chọn file."
    if not os.path.exists(path):
        return False, f"File không tồn tại: {path}"
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]  (Windows-only API)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
        return True, "ok"
    except Exception as e:
        return False, f"Không thể mở file: {e}"
