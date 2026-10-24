"""shortcuts_dialog.py — hộp thoại "⌨ Phím tắt" (F1): liệt kê toàn bộ phím tắt của ứng dụng."""
import customtkinter as ctk
from constants import KB_ESCAPE, SHORTCUT_HELP


class ShortcutsDialog(ctk.CTkToplevel):

    def __init__(self, master):
        super().__init__(master)
        self.title("⌨  Phím tắt")
        self.geometry("460x560")
        self.minsize(380, 360)
        self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(12, 4))
        body.grid_columnconfigure(1, weight=1)
        r = 0
        for group, items in SHORTCUT_HELP:
            ctk.CTkLabel(body, text=group, anchor="w",
                         font=ctk.CTkFont(size=14, weight="bold")
                         ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(12 if r else 0, 4))
            r += 1
            for key, desc in items:
                ctk.CTkLabel(body, text=key, anchor="center", width=150, corner_radius=6,
                             fg_color=("gray85", "gray25"),
                             font=ctk.CTkFont(family="Consolas", size=12, weight="bold")
                             ).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
                ctk.CTkLabel(body, text=desc, anchor="w", justify="left", wraplength=240
                             ).grid(row=r, column=1, sticky="w", pady=2)
                r += 1
        ctk.CTkButton(self, text="Đóng", command=self.destroy, height=34
                      ).pack(pady=(4, 12))
