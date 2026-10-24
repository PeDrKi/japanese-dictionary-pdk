"""
ui/icon_picker.py — chọn icon cho Bộ thẻ / Danh mục từ bộ icon lớn (giống bản web: constants.ICON_GROUPS).

IconPickerField: hàng gồm vài icon hay dùng + nút hiện icon đang chọn; bấm để mở bảng chọn đầy đủ theo nhóm.
Giá trị nằm trong `var` (ctk.StringVar) nên các hộp thoại đọc như trước (`icon_var.get()`).
"""
import customtkinter as ctk

from constants import ICON_GROUPS

QUICK = ["📁", "📚", "🌸", "🎌", "⭐", "🔥", "💎", "🎯"]
_FONT = ("Segoe UI Emoji", 20)


class IconPickerPopup(ctk.CTkToplevel):
    COLS = 10

    def __init__(self, master, current: str, on_pick):
        super().__init__(master)
        self._on_pick = on_pick
        self.title("Chọn icon")
        self.geometry("470x420")
        self.minsize(420, 340)
        self.transient(master.winfo_toplevel())
        self.after(50, self._grab)
        self._current = current
        self._group = ctk.StringVar(value=ICON_GROUPS[0][0])
        names = [n for n, _ in ICON_GROUPS]
        self._chips = ctk.CTkScrollableFrame(self, orientation="horizontal", height=44)
        self._chips.pack(fill="x", padx=10, pady=(10, 4))
        for n in names:
            ctk.CTkRadioButton(self._chips, text=n, variable=self._group, value=n, width=20,
                               command=self._draw).pack(side="left", padx=6)
        self._grid = ctk.CTkScrollableFrame(self)
        self._grid.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self._draw()
        self.bind("<Escape>", lambda e: self.destroy())

    def _grab(self):
        try:
            self.grab_set(); self.lift(); self.focus_force()
        except Exception:
            pass

    def _draw(self):
        for w in self._grid.winfo_children():
            w.destroy()
        icons = dict(ICON_GROUPS)[self._group.get()]
        for i, ic in enumerate(icons):
            on = ic == self._current
            ctk.CTkButton(self._grid, text=ic, width=38, height=38, font=_FONT, corner_radius=8,
                          fg_color=("#3B8ED0", "#1F6AA5") if on else "transparent",
                          hover_color=("gray80", "gray30"), text_color=("gray10", "gray90"),
                          command=lambda x=ic: self._choose(x)).grid(row=i // self.COLS, column=i % self.COLS, padx=1, pady=1)

    def _choose(self, icon):
        self._on_pick(icon)
        self.destroy()


class IconPickerField(ctk.CTkFrame):
    """Dùng: `IconPickerField(parent, var).pack(...)` — var là ctk.StringVar giữ icon đang chọn."""

    def __init__(self, master, var: ctk.StringVar):
        super().__init__(master, fg_color="transparent")
        self.var = var
        self._quick = ctk.CTkFrame(self, fg_color="transparent")
        self._quick.pack(side="left")
        for ic in QUICK:
            ctk.CTkButton(self._quick, text=ic, width=32, height=32, font=("Segoe UI Emoji", 16), corner_radius=6,
                          fg_color="transparent", hover_color=("gray80", "gray30"), text_color=("gray10", "gray90"),
                          command=lambda x=ic: self._set(x)).pack(side="left", padx=1)
        self._btn = ctk.CTkButton(self, text="", width=110, height=32, command=self._open)
        self._btn.pack(side="left", padx=(8, 0))
        var.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _refresh(self):
        self._btn.configure(text=f"{self.var.get() or '📁'}  Thêm icon…")

    def _set(self, icon):
        self.var.set(icon)

    def _open(self):
        IconPickerPopup(self, self.var.get(), self._set)
