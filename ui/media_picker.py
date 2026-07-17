"""
media_picker.py — reusable audio + image attachment picker widget.

Extracted from ui/card_form.py (which was growing into a large do-everything
file) so this piece owns its own state and can be tested/reused on its own.
The parent form just embeds it and reads .get_paths() when saving.
"""
import customtkinter as ctk
import os
from tkinter import filedialog


class MediaPicker(ctk.CTkFrame):
    """
    Two-row widget:
      🔊 Chọn âm thanh   [filename]   ✕
      🖼️ Chọn ảnh        [filename]   ✕

    Usage:
        picker = MediaPicker(parent, audio_path=card.get("audio_path"),
                                      image_path=card.get("image_path"))
        picker.pack(fill="x", ...)
        ...
        audio_path, image_path = picker.get_paths()
    """

    def __init__(self, master, audio_path=None, image_path=None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._audio_path = audio_path
        self._image_path = image_path
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(self, text="🔊 Chọn âm thanh", width=140,
                      command=self._pick_audio).grid(row=0, column=0, sticky="w")
        self._audio_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11),
                                        text_color=("gray50", "gray55"), anchor="w")
        self._audio_lbl.grid(row=0, column=1, sticky="w", padx=(10, 4))
        ctk.CTkButton(self, text="✕", width=28, fg_color=("gray75", "gray35"),
                      text_color=("gray10", "gray90"),
                      command=self._clear_audio).grid(row=0, column=2, sticky="w")

        ctk.CTkButton(self, text="🖼️ Chọn ảnh", width=140,
                      command=self._pick_image).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self._image_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11),
                                        text_color=("gray50", "gray55"), anchor="w")
        self._image_lbl.grid(row=1, column=1, sticky="w", padx=(10, 4), pady=(8, 0))
        ctk.CTkButton(self, text="✕", width=28, fg_color=("gray75", "gray35"),
                      text_color=("gray10", "gray90"),
                      command=self._clear_image).grid(row=1, column=2, sticky="w", pady=(8, 0))

        self._refresh_labels()

    def _refresh_labels(self):
        self._audio_lbl.configure(
            text=os.path.basename(self._audio_path) if self._audio_path else "Chưa chọn")
        self._image_lbl.configure(
            text=os.path.basename(self._image_path) if self._image_path else "Chưa chọn")

    def _pick_audio(self):
        path = filedialog.askopenfilename(
            title="Chọn file âm thanh", parent=self.winfo_toplevel(),
            filetypes=[("Âm thanh", "*.mp3 *.wav *.ogg *.m4a *.flac"), ("Tất cả file", "*.*")])
        if path:
            self._audio_path = path
            self._refresh_labels()

    def _clear_audio(self):
        self._audio_path = None
        self._refresh_labels()

    def _pick_image(self):
        path = filedialog.askopenfilename(
            title="Chọn ảnh minh họa", parent=self.winfo_toplevel(),
            filetypes=[("Ảnh", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("Tất cả file", "*.*")])
        if path:
            self._image_path = path
            self._refresh_labels()

    def _clear_image(self):
        self._image_path = None
        self._refresh_labels()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_paths(self):
        """Return (audio_path, image_path) — either may be None."""
        return self._audio_path, self._image_path

    def reset(self):
        """Clear both attachments. Used by CardForm's "Lưu & Thêm tiếp" so
        the next card doesn't inherit the previous one's audio/image."""
        self._audio_path = None
        self._image_path = None
        self._refresh_labels()
