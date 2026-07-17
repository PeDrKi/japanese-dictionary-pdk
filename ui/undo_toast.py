"""
undo_toast.py — reusable "🗑️ Đã xóa X — [↩ Hoàn tác]" toast notification.

Extracted from ui/table_view.py. Self-contained: owns its own placement,
auto-dismiss timer, and undo button; the parent just supplies a message
and an on_undo callback.
"""
import customtkinter as ctk


class UndoToast(ctk.CTkFrame):
    """
    A floating toast anchored to the bottom-center of its master, with an
    "↩ Hoàn tác" (undo) button and a 5-second auto-dismiss timer.

    Usage:
        UndoToast.show(self, message=f"🗑️ Đã chuyển «{card['character']}» vào thùng rác",
                        on_undo=lambda: restore_card(card['id']))
    """

    AUTO_DISMISS_MS = 5000

    def __init__(self, master, message: str, on_undo, **kwargs):
        kwargs.setdefault("fg_color", ("#1a3a5c", "#1a3a5c"))
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("height", 44)
        super().__init__(master, **kwargs)
        self._on_undo = on_undo
        self._build(message)

    def _build(self, message):
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=message, font=ctk.CTkFont(size=12),
                     text_color="white", anchor="w"
                     ).grid(row=0, column=0, padx=14, pady=10, sticky="w")
        ctk.CTkButton(self, text="↩ Hoàn tác", width=90, height=28,
                      corner_radius=6, fg_color="#2563EB", hover_color="#1d4ed8",
                      text_color="white", font=ctk.CTkFont(size=11),
                      command=self._handle_undo
                      ).grid(row=0, column=1, padx=(0, 8), pady=8)
        self.after(self.AUTO_DISMISS_MS, self._auto_dismiss)

    def _handle_undo(self):
        if self.winfo_exists():
            self.destroy()
        if self._on_undo:
            self._on_undo()

    def _auto_dismiss(self):
        if self.winfo_exists():
            self.destroy()

    @classmethod
    def show(cls, master, message: str, on_undo):
        """
        Place a new toast at the bottom-center of `master`, replacing any
        toast already showing there (tracked via master._toast).
        """
        if hasattr(master, "_toast") and master._toast.winfo_exists():
            master._toast.destroy()
        toast = cls(master, message, on_undo)
        toast.place(relx=0.5, rely=1.0, anchor="s", relwidth=0.6, y=-56)
        master._toast = toast
        return toast
