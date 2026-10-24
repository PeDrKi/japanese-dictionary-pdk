"""
ui/grammar_view.py — màn "📖 Ngữ pháp": danh sách mẫu câu bên trái, chi tiết (cấu tạo, giải thích, ví dụ) bên phải.
Cùng dữ liệu với tab Ngữ pháp của bản web (đồng bộ qua Supabase).
"""
import logging
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from constants import KB_ESCAPE, KB_SAVE, JLPT_LEVELS
from domain.notes import parse_examples

logger = logging.getLogger(__name__)


class _EntryText:
    """Đọc nội dung ô tìm kiếm (CTkEntry có placeholder không dùng được textvariable)."""
    def __init__(self, entry):
        self._e = entry

    def get(self):
        return self._e.get()
JP_FONT = "Noto Sans JP"


class GrammarDialog(ctk.CTkToplevel):
    """Thêm / sửa một mẫu ngữ pháp. `preset` điền sẵn khi thêm mới (vd ví dụ lấy từ Bản dịch)."""

    def __init__(self, master, service, on_saved, gid=None, preset=None):
        super().__init__(master)
        self._svc, self._on_saved, self._gid = service, on_saved, gid
        g = (service.get_grammar(gid) if gid else None) or dict(preset or {})
        self.title("✏️  Sửa ngữ pháp" if gid else "➕  Thêm ngữ pháp")
        self.geometry("560x680")
        self.minsize(480, 520)
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        self.bind(KB_SAVE, lambda _: self._save())

        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True)
        p = dict(padx=20, pady=(10, 2), anchor="w")
        ctk.CTkLabel(body, text="Mẫu câu *", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.title_e = ctk.CTkEntry(body, placeholder_text="VD: 〜てから", font=ctk.CTkFont(family=JP_FONT, size=16))
        self.title_e.pack(fill="x", padx=20)
        self.title_e.insert(0, g.get("title") or "")
        ctk.CTkLabel(body, text="Ý nghĩa", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.mean_e = ctk.CTkEntry(body, placeholder_text="sau khi …")
        self.mean_e.pack(fill="x", padx=20)
        self.mean_e.insert(0, g.get("meaning_vi") or "")
        row = ctk.CTkFrame(body, fg_color="transparent"); row.pack(fill="x", padx=20, pady=(10, 0))
        ctk.CTkLabel(row, text="JLPT", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.jlpt_var = ctk.StringVar(value=g.get("jlpt_level") or "—")
        ctk.CTkOptionMenu(row, values=["—"] + list(JLPT_LEVELS), variable=self.jlpt_var, width=90).pack(side="left", padx=10)
        ctk.CTkLabel(body, text="Cấu tạo", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.struct_e = ctk.CTkEntry(body, placeholder_text="V-て + から", font=ctk.CTkFont(family=JP_FONT, size=14))
        self.struct_e.pack(fill="x", padx=20)
        self.struct_e.insert(0, g.get("structure") or "")
        ctk.CTkLabel(body, text="Giải thích / cách dùng / lưu ý", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.expl_t = ctk.CTkTextbox(body, height=110, wrap="word")
        self.expl_t.pack(fill="x", padx=20)
        self.expl_t.insert("1.0", g.get("explanation") or "")
        ctk.CTkLabel(body, text="Ví dụ (mỗi dòng: câu tiếng Nhật | nghĩa tiếng Việt)", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.ex_t = ctk.CTkTextbox(body, height=170, wrap="word", font=ctk.CTkFont(family=JP_FONT, size=14))
        self.ex_t.pack(fill="x", padx=20, pady=(0, 10))
        self.ex_t.insert("1.0", g.get("examples") or "")

        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(bar, text="✕  Hủy", width=90, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
                      command=self.destroy).pack(side="left")
        if gid:
            ctk.CTkButton(bar, text="🗑  Xóa", width=80, fg_color="#c0392b", hover_color="#922b21", command=self._delete).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="💾  Lưu", height=36, command=self._save).pack(side="right")
        self.title_e.focus_set()

    def _save(self):
        j = self.jlpt_var.get()
        data = {"title": self.title_e.get(), "meaning_vi": self.mean_e.get(), "structure": self.struct_e.get(),
                "explanation": self.expl_t.get("1.0", "end-1c"), "examples": self.ex_t.get("1.0", "end-1c"),
                "jlpt_level": "" if j == "—" else j}
        gid, err = self._svc.save_grammar(self._gid, data)
        if err:
            self.title_e.configure(border_color="red")
            return messagebox.showwarning("Chưa lưu", err, parent=self)
        self._on_saved(gid)
        self.destroy()

    def _delete(self):
        if messagebox.askyesno("Xóa", "Xóa mẫu ngữ pháp này? Không thể hoàn tác.", parent=self):
            self._svc.delete_grammar(self._gid)
            self._on_saved(None)
            self.destroy()


class GrammarView(ctk.CTkFrame):
    def __init__(self, master, material_service):
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self._svc = material_service
        self._sel = None
        self._jlpt = ""
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        top = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray90", "gray18"), height=50)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(top, text="📖  Ngữ pháp", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=14, pady=10)
        self.search_e = ctk.CTkEntry(top, width=260, placeholder_text="Tìm mẫu câu, nghĩa, ví dụ…")
        self.search_e.pack(side="left", padx=8)
        self.search_e.bind("<KeyRelease>", lambda _: self._debounce())
        self.search_var = _EntryText(self.search_e)
        self.jlpt_menu = ctk.CTkOptionMenu(top, values=["Mọi cấp"] + list(JLPT_LEVELS), width=100, command=self._on_jlpt)
        self.jlpt_menu.pack(side="left", padx=4)
        ctk.CTkButton(top, text="➕  Thêm", width=90, command=lambda: self.open_form(None)).pack(side="right", padx=14, pady=9)
        self.count_lbl = ctk.CTkLabel(top, text="", text_color=("gray40", "gray60"))
        self.count_lbl.pack(side="right", padx=8)

        self.listbox = ctk.CTkScrollableFrame(self, width=320, corner_radius=0)
        self.listbox.grid(row=1, column=0, sticky="nsew")
        self.detail = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        self.detail.grid(row=1, column=1, sticky="nsew")
        self._timer = None
        self.refresh()

    # ── dữ liệu ──
    def _debounce(self):
        if self._timer:
            self.after_cancel(self._timer)
        self._timer = self.after(200, self.refresh)

    def _on_jlpt(self, v):
        self._jlpt = "" if v == "Mọi cấp" else v
        self.refresh()

    def refresh(self, force=None):
        self._timer = None
        items = self._svc.list_grammar(self.search_var.get(), self._jlpt)
        self.count_lbl.configure(text=f"{len(items)} mẫu")
        for w in self.listbox.winfo_children():
            w.destroy()
        if not items:
            ctk.CTkLabel(self.listbox, text="Chưa có mẫu ngữ pháp nào.\nBấm “➕ Thêm” để bắt đầu.", justify="center",
                         text_color=("gray40", "gray60")).pack(pady=40)
        ids = {g["id"] for g in items}
        if self._sel not in ids:
            self._sel = items[0]["id"] if items else None
        for g in items:
            on = g["id"] == self._sel
            b = ctk.CTkButton(self.listbox, anchor="w", height=52, corner_radius=8,
                              fg_color=("#3B8ED0", "#1F6AA5") if on else ("gray88", "gray22"),
                              hover_color=("gray78", "gray30"), text_color="white" if on else ("gray10", "gray90"),
                              text=f"{g['title']}" + (f"   [{g['jlpt_level']}]" if g.get("jlpt_level") else "") + f"\n{g.get('meaning_vi') or ''}",
                              font=ctk.CTkFont(family=JP_FONT, size=13),
                              command=lambda i=g["id"]: self.select(i))
            b.pack(fill="x", padx=6, pady=2)
        self._draw_detail()

    def select(self, gid):
        self._sel = gid
        self.refresh()

    def open_form(self, gid, preset=None):
        GrammarDialog(self.winfo_toplevel(), self._svc, on_saved=self._after_save, gid=gid, preset=preset)

    def _after_save(self, gid):
        if gid:
            self._sel = gid
        self.refresh()

    # ── chi tiết ──
    def _draw_detail(self):
        for w in self.detail.winfo_children():
            w.destroy()
        g = self._svc.get_grammar(self._sel) if self._sel else None
        if not g:
            return
        head = ctk.CTkFrame(self.detail, fg_color="transparent"); head.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(head, text=g["title"], font=ctk.CTkFont(family=JP_FONT, size=30, weight="bold")).pack(side="left")
        ctk.CTkButton(head, text="✏️ Sửa", width=80, command=lambda: self.open_form(g["id"])).pack(side="right")
        if g.get("jlpt_level"):
            ctk.CTkLabel(head, text=g["jlpt_level"], fg_color="#6C5CE7", corner_radius=8, text_color="white",
                         font=ctk.CTkFont(size=11, weight="bold"), width=40).pack(side="right", padx=10)
        if g.get("meaning_vi"):
            ctk.CTkLabel(self.detail, text=g["meaning_vi"], font=ctk.CTkFont(size=16), anchor="w", justify="left",
                         wraplength=520).pack(fill="x", padx=20, pady=(0, 8))

        def section(title, text, jp=False):
            if not text:
                return
            ctk.CTkLabel(self.detail, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray40", "gray60"),
                         anchor="w").pack(fill="x", padx=20, pady=(10, 0))
            ctk.CTkLabel(self.detail, text=text, anchor="w", justify="left", wraplength=520,
                         font=ctk.CTkFont(family=JP_FONT if jp else None, size=15 if jp else 13)).pack(fill="x", padx=20)
        section("Cấu tạo", g.get("structure"), jp=True)
        section("Giải thích", g.get("explanation"))
        exs = parse_examples(g.get("examples"))
        if exs:
            ctk.CTkLabel(self.detail, text=f"Ví dụ ({len(exs)})", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=("gray40", "gray60"), anchor="w").pack(fill="x", padx=20, pady=(14, 2))
            for jp, vi in exs:
                card = ctk.CTkFrame(self.detail, corner_radius=8, fg_color=("gray90", "gray20")); card.pack(fill="x", padx=20, pady=3)
                ctk.CTkLabel(card, text=jp, anchor="w", justify="left", wraplength=500,
                             font=ctk.CTkFont(family=JP_FONT, size=15)).pack(fill="x", padx=12, pady=(8, 0 if vi else 8))
                if vi:
                    ctk.CTkLabel(card, text=vi, anchor="w", justify="left", wraplength=500,
                                 text_color=("gray35", "gray65")).pack(fill="x", padx=12, pady=(0, 8))
