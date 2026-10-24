"""
sync_toast.py — toast nhỏ báo kết quả sync tự động (lúc mở app), không có
nút hoàn tác (khác UndoToast). 2 kiểu:
  - "success": nền xanh, chỉ hiện khi sync THỰC SỰ kéo/gộp được gì đó —
    im lặng hoàn toàn nếu không có gì thay đổi, tránh làm phiền mỗi lần
    mở app.
  - "error": nền cam/đỏ nhạt, có thể bấm vào để mở dialog Sync đầy đủ
    xem chi tiết lỗi.
"""
import customtkinter as ctk

_COLORS = {
    "success": {"fg": ("#1a4d2e", "#1a4d2e"), "hover": ("#1a4d2e", "#1a4d2e")},
    "error":   {"fg": ("#5c2e1a", "#5c2e1a"), "hover": ("#6b3820", "#6b3820")},
}


class SyncToast(ctk.CTkFrame):
    AUTO_DISMISS_MS = {"success": 4000, "error": 9000}

    def __init__(self, master, message: str, variant: str = "success", on_click=None, **kwargs):
        colors = _COLORS.get(variant, _COLORS["success"])
        kwargs.setdefault("fg_color", colors["fg"])
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("height", 40)
        kwargs.setdefault("width", 320)
        super().__init__(master, **kwargs)
        self._on_click = on_click
        self._variant  = variant
        self._build(message, clickable=on_click is not None)
        self.after(self.AUTO_DISMISS_MS.get(variant, 4000), self._auto_dismiss)

    def _build(self, message, clickable: bool):
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(
            self, text=message, font=ctk.CTkFont(size=12),
            text_color="white", anchor="w",
            cursor="hand2" if clickable else "arrow",
        )
        label.grid(row=0, column=0, padx=14, pady=9, sticky="w")
        if clickable:
            label.bind("<Button-1>", lambda e: self._handle_click())
            self.bind("<Button-1>", lambda e: self._handle_click())

    def _handle_click(self):
        if self.winfo_exists():
            self.destroy()
        if self._on_click:
            self._on_click()

    def _auto_dismiss(self):
        if self.winfo_exists():
            self.destroy()

    @classmethod
    def show(cls, master, message: str, variant: str = "success", on_click=None):
        """Đặt toast ở góc dưới-phải (khác UndoToast ở giữa-dưới, để
        không đè lên nhau nếu cả 2 cùng xuất hiện)."""
        if hasattr(master, "_sync_toast") and master._sync_toast.winfo_exists():
            master._sync_toast.destroy()
        toast = cls(master, message, variant, on_click)
        toast.place(relx=1.0, rely=1.0, anchor="se", x=-16, y=-16)
        master._sync_toast = toast
        return toast
