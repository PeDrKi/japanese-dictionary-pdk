"""
tooltip.py — Lightweight hover tooltip for CustomTkinter widgets.
Usage:
    btn = ctk.CTkButton(...)
    Tooltip(btn, "Thêm thẻ mới  (Ctrl+N)")
"""
import customtkinter as ctk
import tkinter as tk


class Tooltip:
    """
    Show a small popup label when the user hovers over a widget.
    Dismisses automatically on mouse-leave or after 4 seconds.
    """

    _DELAY_MS  = 500    # ms before showing
    _HIDE_MS   = 4000   # ms before auto-hiding

    def __init__(self, widget, text: str, max_width: int = 260):
        self._widget    = widget
        self._text      = text
        self._max_width = max_width
        self._tip_win   = None
        self._after_id  = None
        self._hide_id   = None

        widget.bind("<Enter>",  self._schedule_show, add="+")
        widget.bind("<Leave>",  self._hide,          add="+")
        widget.bind("<Button>", self._hide,          add="+")

    # ── Public ────────────────────────────────────────────────────────────────

    def update_text(self, text: str):
        self._text = text
        if self._tip_win:
            self._hide()

    def destroy(self):
        self._hide()
        try:
            self._widget.unbind("<Enter>")
            self._widget.unbind("<Leave>")
            self._widget.unbind("<Button>")
        except Exception:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _schedule_show(self, _event=None):
        self._cancel_pending()
        self._after_id = self._widget.after(self._DELAY_MS, lambda: (self._show() if self._widget.winfo_exists() else None))

    def _show(self):
        if self._tip_win:
            return
        try:
            x = self._widget.winfo_rootx() + self._widget.winfo_width() // 2
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        except Exception:
            return

        dark = ctk.get_appearance_mode() == "Dark"
        bg   = "#1e2130" if dark else "#ffffea"
        fg   = "#e8eaf0" if dark else "#1a1a2e"
        bd   = "#3d4455" if dark else "#ccccaa"

        win = tk.Toplevel(self._widget)
        win.wm_overrideredirect(True)
        win.wm_geometry(f"+{x}+{y}")
        win.attributes("-topmost", True)
        if dark:
            win.configure(bg=bd)

        lbl = tk.Label(
            win, text=self._text,
            background=bg, foreground=fg,
            font=("Segoe UI", 10),
            relief="flat",
            padx=8, pady=4,
            wraplength=self._max_width,
            justify="left",
        )
        lbl.pack()

        # Border via frame on dark mode
        if dark:
            win.configure(padx=1, pady=1)

        self._tip_win = win
        self._hide_id = self._widget.after(self._HIDE_MS, lambda: (self._hide() if self._widget.winfo_exists() else None))

    def _hide(self, _event=None):
        self._cancel_pending()
        if self._tip_win:
            try:
                self._tip_win.destroy()
            except Exception:
                pass
            self._tip_win = None

    def _cancel_pending(self):
        for attr in ("_after_id", "_hide_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self._widget.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
