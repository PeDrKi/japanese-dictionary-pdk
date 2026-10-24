"""
ui/translation_view.py — màn "訳 Bản dịch": dán câu / đoạn / bài văn tiếng Nhật, ghi nghĩa tiếng Việt, kèm cột từ vựng.

Trang đọc chia hai bên giống bản web: trái là bài tiếng Nhật (từ trong cột từ vựng gạch chân đỏ), phải có 2 tab
"Từ vựng" và "Bản dịch". Bôi đen chữ trong bài → ghi vào cột từ vựng / tạo thẻ từ vựng / thêm làm ví dụ ngữ pháp.
"""
import logging
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from constants import KB_ESCAPE, KB_SAVE, JLPT_LEVELS
from domain.notes import find_spans, parse_glossary, sentence_of, split_paras, example_line
from ui.card_form import CardForm

logger = logging.getLogger(__name__)


class _EntryText:
    """Đọc nội dung ô tìm kiếm (CTkEntry có placeholder không dùng được textvariable)."""
    def __init__(self, entry):
        self._e = entry

    def get(self):
        return self._e.get()
JP_FONT = "Noto Sans JP"
RED = "#E5484D"
MODES = (("two", "Hai bên"), ("pair", "Đối chiếu"), ("hide", "Che bản dịch"), ("jp", "Chỉ tiếng Nhật"))


def _clip(s, n):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _colors():
    dark = ctk.get_appearance_mode() == "Dark"
    return dict(bg="#1e2130" if dark else "#ffffff", fg="#e8eaf0" if dark else "#1a1a2e",
                mute="#8a90a6" if dark else "#6b7186", cover="#3a4058" if dark else "#d5d9e6")


class TranslationDialog(ctk.CTkToplevel):
    def __init__(self, master, service, on_saved, tid=None):
        super().__init__(master)
        self._svc, self._on_saved, self._tid = service, on_saved, tid
        t = (service.get_translation(tid) if tid else None) or {}
        self.title("✏️  Sửa bản dịch" if tid else "➕  Thêm bản dịch")
        self.geometry("720x760"); self.minsize(600, 560)
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy()); self.bind(KB_SAVE, lambda _: self._save())
        body = ctk.CTkScrollableFrame(self); body.pack(fill="both", expand=True)
        p = dict(padx=20, pady=(10, 2), anchor="w")
        row = ctk.CTkFrame(body, fg_color="transparent"); row.pack(fill="x", padx=20, pady=(12, 0))
        self.title_e = ctk.CTkEntry(row, placeholder_text="Tiêu đề (không bắt buộc)", font=ctk.CTkFont(family=JP_FONT, size=14))
        self.title_e.pack(side="left", fill="x", expand=True); self.title_e.insert(0, t.get("title") or "")
        self.jlpt_var = ctk.StringVar(value=t.get("jlpt_level") or "—")
        ctk.CTkOptionMenu(row, values=["—"] + list(JLPT_LEVELS), variable=self.jlpt_var, width=80).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(body, text="Tiếng Nhật *  (mỗi dòng là một đoạn)", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.jp_t = ctk.CTkTextbox(body, height=190, wrap="word", font=ctk.CTkFont(family=JP_FONT, size=15)); self.jp_t.pack(fill="x", padx=20)
        self.jp_t.insert("1.0", t.get("jp") or "")
        ctk.CTkLabel(body, text="Tiếng Việt  (mỗi dòng ứng với một đoạn tiếng Nhật)", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.vi_t = ctk.CTkTextbox(body, height=170, wrap="word"); self.vi_t.pack(fill="x", padx=20)
        self.vi_t.insert("1.0", t.get("vi") or "")
        self.info = ctk.CTkLabel(body, text="", text_color=("gray40", "gray60"), anchor="w"); self.info.pack(fill="x", padx=20)
        ctk.CTkLabel(body, text="Từ vựng  (mỗi dòng:  từ = nghĩa)", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.gl_t = ctk.CTkTextbox(body, height=120, wrap="word", font=ctk.CTkFont(family=JP_FONT, size=13)); self.gl_t.pack(fill="x", padx=20)
        self.gl_t.insert("1.0", t.get("glossary") or "")
        ctk.CTkLabel(body, text="Ghi chú", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.note_t = ctk.CTkTextbox(body, height=70, wrap="word"); self.note_t.pack(fill="x", padx=20, pady=(0, 10))
        self.note_t.insert("1.0", t.get("note") or "")
        for w in (self.jp_t, self.vi_t):
            w.bind("<KeyRelease>", lambda _: self._count())
        self._count()
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(fill="x", padx=20, pady=10)
        ctk.CTkButton(bar, text="✕  Hủy", width=90, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=self.destroy).pack(side="left")
        if tid:
            ctk.CTkButton(bar, text="🗑  Xóa", width=80, fg_color="#c0392b", hover_color="#922b21", command=self._delete).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="💾  Lưu", height=36, command=self._save).pack(side="right")
        self.jp_t.focus_set()

    def _count(self):
        jp, vi = split_paras(self.jp_t.get("1.0", "end-1c")), split_paras(self.vi_t.get("1.0", "end-1c"))
        n = len("".join(jp))
        m = f"{n} chữ · {len(jp)} đoạn tiếng Nhật"
        if vi:
            m += f" · {len(vi)} đoạn tiếng Việt — " + ("khớp, sẽ đối chiếu từng đoạn" if len(vi) == len(jp) else "chưa khớp số đoạn")
        self.info.configure(text=m)

    def _save(self):
        j = self.jlpt_var.get()
        data = {"title": self.title_e.get(), "jp": self.jp_t.get("1.0", "end-1c"), "vi": self.vi_t.get("1.0", "end-1c"),
                "glossary": self.gl_t.get("1.0", "end-1c"), "note": self.note_t.get("1.0", "end-1c"), "jlpt_level": "" if j == "—" else j}
        tid, err = self._svc.save_translation(self._tid, data)
        if err:
            return messagebox.showwarning("Chưa lưu", err, parent=self)
        self._on_saved(tid); self.destroy()

    def _delete(self):
        if messagebox.askyesno("Xóa", "Xóa bản dịch này? Không thể hoàn tác.", parent=self):
            self._svc.delete_translation(self._tid); self._on_saved(None); self.destroy()


class GlossDialog(ctk.CTkToplevel):
    def __init__(self, master, service, tid, index, preset, on_done, to_card):
        super().__init__(master)
        self._svc, self._tid, self._i, self._on_done, self._to_card = service, tid, index, on_done, to_card
        g = (service.glossary(tid)[index] if index is not None else {"term": preset or "", "meaning": ""})
        self.title("Sửa từ vựng" if index is not None else "Thêm từ vào cột từ vựng")
        self.geometry("420x290"); self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy()); self.bind("<Return>", lambda _: self._save())
        p = dict(padx=20, pady=(14, 2), anchor="w")
        ctk.CTkLabel(self, text="Từ / cụm từ *", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.term_e = ctk.CTkEntry(self, font=ctk.CTkFont(family=JP_FONT, size=16)); self.term_e.pack(fill="x", padx=20); self.term_e.insert(0, g["term"])
        ctk.CTkLabel(self, text="Nghĩa", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.mean_e = ctk.CTkEntry(self); self.mean_e.pack(fill="x", padx=20); self.mean_e.insert(0, g["meaning"])
        if index is not None:
            ctk.CTkButton(self, text="Lưu thành thẻ từ vựng…", fg_color="transparent", hover=False, text_color=("#1F6AA5", "#6CB4EE"),
                          anchor="w", command=self._card).pack(anchor="w", padx=14, pady=(8, 0))
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(side="bottom", fill="x", padx=20, pady=14)
        ctk.CTkButton(bar, text="Hủy", width=80, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=self.destroy).pack(side="left")
        if index is not None:
            ctk.CTkButton(bar, text="🗑 Xóa", width=70, fg_color="#c0392b", hover_color="#922b21", command=self._delete).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="💾  Lưu", command=self._save).pack(side="right")
        (self.mean_e if g["term"] else self.term_e).focus_set()

    def _save(self):
        if not self.term_e.get().strip():
            return
        self._svc.set_glossary_term(self._tid, self._i, self.term_e.get(), self.mean_e.get())
        self._on_done(); self.destroy()

    def _delete(self):
        self._svc.delete_glossary_term(self._tid, self._i); self._on_done(); self.destroy()

    def _card(self):
        term, mean = self.term_e.get().strip(), self.mean_e.get().strip()
        self.destroy(); self._to_card(term, mean)


class GrammarPickDialog(ctk.CTkToplevel):
    """Thêm câu / đoạn đã chọn làm ví dụ cho một mẫu ngữ pháp (có sẵn hoặc mới)."""

    def __init__(self, master, service, sel, on_new):
        super().__init__(master)
        self._svc, self._sel, self._on_new = service, sel, on_new
        self.title("Thêm làm ví dụ ngữ pháp"); self.geometry("520x600")
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        picked = sel["text"] if len(sel["text"]) >= 8 or any(c in sel["text"] for c in "。！？") else sel["sentence"]
        self._scopes = {"sel": ("Phần đã chọn", picked), "sen": ("Cả câu", sel["sentence"]), "par": ("Cả đoạn", sel["paragraph"])}
        order = [k for k in ("sel", "sen", "par")
                 if not (k == "sel" and picked in (sel["sentence"], sel["paragraph"])) and not (k == "sen" and sel["sentence"] == sel["paragraph"])]
        self._scope = "sen" if picked == sel["sentence"] and "sen" in order else ("sel" if "sel" in order else order[-1])
        self.seg = ctk.CTkSegmentedButton(self, values=[self._scopes[k][0] for k in order], command=self._on_scope)
        self._order = order
        self.seg.set(self._scopes[self._scope][0]); self.seg.pack(padx=16, pady=(14, 6), anchor="w")
        self.prev = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=480, fg_color=("gray90", "gray20"), corner_radius=8,
                                 font=ctk.CTkFont(family=JP_FONT, size=14))
        self.prev.pack(fill="x", padx=16, pady=4, ipady=8)
        self.q = ctk.StringVar(); ctk.CTkEntry(self, textvariable=self.q, placeholder_text="Tìm mẫu ngữ pháp…").pack(fill="x", padx=16, pady=6)
        self.q.trace_add("write", lambda *_: self._draw())
        self.lst = ctk.CTkScrollableFrame(self); self.lst.pack(fill="both", expand=True, padx=10)
        ctk.CTkButton(self, text="＋ Tạo mẫu ngữ pháp mới với ví dụ này", command=self._new).pack(fill="x", padx=16, pady=10)
        self._on_scope(self._scopes[self._scope][0]); self._draw()

    def _line(self):
        jp = self._scopes[self._scope][1]
        s = self._sel
        return example_line(jp, s["vi"] if s["vi"] and s["paragraph"] == jp else "")

    def _on_scope(self, label):
        self._scope = next(k for k in self._order if self._scopes[k][0] == label)
        self.prev.configure(text=self._line())

    def _draw(self):
        for w in self.lst.winfo_children():
            w.destroy()
        items = self._svc.list_grammar(self.q.get())[:40]
        for g in items:
            ctk.CTkButton(self.lst, text=f"{g['title']}\n{g.get('meaning_vi') or ''}", anchor="w", height=48, fg_color=("gray88", "gray22"),
                          text_color=("gray10", "gray90"), hover_color=("gray78", "gray30"), font=ctk.CTkFont(family=JP_FONT, size=13),
                          command=lambda i=g["id"], t=g["title"]: self._add(i, t)).pack(fill="x", pady=2, padx=4)
        if not items:
            ctk.CTkLabel(self.lst, text="Chưa có mẫu nào khớp.", text_color=("gray40", "gray60")).pack(pady=20)

    def _add(self, gid, title):
        st = self._svc.add_example(gid, self._line())
        if st == "toolong":
            return messagebox.showwarning("Quá dài", "Mẫu này đã có quá nhiều ví dụ.", parent=self)
        messagebox.showinfo("Ngữ pháp", "Ví dụ này đã có trong mẫu." if st == "dup" else f"Đã thêm ví dụ vào {title}.", parent=self)
        self.destroy()

    def _new(self):
        line = self._line(); self.destroy(); self._on_new(line)


class BulkCardsDialog(ctk.CTkToplevel):
    """Chọn các từ trong cột từ vựng → tạo thẻ + xếp vào bộ thẻ."""

    def __init__(self, master, service, t, decks, recent, on_done):
        super().__init__(master)
        self._svc, self._t, self._on_done = service, t, on_done
        self.title("Thêm từ vào bộ thẻ"); self.geometry("480x600")
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        ctk.CTkLabel(self, text="Chọn từ cần thêm. Câu chứa từ trong bài làm câu ví dụ, nguồn = tên bài.", wraplength=440, justify="left",
                     text_color=("gray40", "gray60")).pack(padx=16, pady=(12, 4), anchor="w")
        body = ctk.CTkScrollableFrame(self); body.pack(fill="both", expand=True, padx=10)
        self._vars = []
        for g in parse_glossary(t.get("glossary")):
            dup = service.card_exists(g["term"]); ok = bool(g["meaning"]) and not dup
            v = ctk.BooleanVar(value=ok); self._vars.append(v)
            ctk.CTkCheckBox(body, variable=v, state="normal" if ok else "disabled", font=ctk.CTkFont(family=JP_FONT, size=14),
                            text=f"{g['term']} = {g['meaning'] or '—'}" + ("   (đã có thẻ)" if dup else "   (chưa có nghĩa)" if not g["meaning"] else "")
                            ).pack(anchor="w", pady=3, padx=6)
        ctk.CTkLabel(self, text="Bộ thẻ", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=16, pady=(8, 0))
        dbox = ctk.CTkScrollableFrame(self, height=100, orientation="vertical"); dbox.pack(fill="x", padx=10)
        self._dvars = {}
        for d in decks:
            v = ctk.BooleanVar(value=d["id"] in recent[:1]); self._dvars[d["id"]] = v
            ctk.CTkCheckBox(dbox, variable=v, text=f"{d.get('icon') or '📁'}  {d['name']}").pack(anchor="w", pady=2, padx=6)
        if not decks:
            ctk.CTkLabel(dbox, text="Chưa có bộ thẻ — thẻ sẽ vào Thư viện.", text_color=("gray40", "gray60")).pack(pady=8)
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(bar, text="Hủy", width=80, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=self.destroy).pack(side="left")
        ctk.CTkButton(bar, text="Thêm thẻ", command=self._go).pack(side="right")

    def _go(self):
        picks = [i for i, v in enumerate(self._vars) if v.get()]
        if not picks:
            return
        decks = [d for d, v in self._dvars.items() if v.get()]
        made, skipped = self._svc.cards_from_glossary(self._t["id"], picks, decks)
        messagebox.showinfo("Đã thêm", f"Đã tạo {made} thẻ" + (f" ({skipped} bỏ qua)" if skipped else "") + (" và xếp vào bộ thẻ." if decks and made else "."), parent=self)
        self._on_done(decks); self.destroy()


class TranslationsView(ctk.CTkFrame):
    def __init__(self, master, material_service, card_service, deck_service, grammar_view=None, on_cards_changed=None):
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self._svc, self._cards, self._decks = material_service, card_service, deck_service
        self._grammar_view = grammar_view
        self._on_cards_changed = on_cards_changed or (lambda: None)
        self._open = None           # id bài đang đọc
        self._mode, self._side = "two", "gloss"
        self._sel = None
        self._jlpt = ""
        self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(0, weight=1)
        self._top = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray90", "gray18"), height=50)
        self._top.grid(row=0, column=0, sticky="ew")
        self._body = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self._body.grid(row=1, column=0, sticky="nsew")
        self._body.grid_rowconfigure(0, weight=1); self._body.grid_columnconfigure(0, weight=1)
        self._q = ""; self._timer = None
        self.refresh()

    # ── điều hướng ──
    def refresh(self, force=None):
        self._timer = None
        if self._open and self._svc.get_translation(self._open):
            self._show_reader()
        else:
            self._open = None
            self._show_list()

    def _clear(self):
        for f in (self._top, self._body):
            for w in f.winfo_children():
                w.destroy()
        self._sel = None

    # ── danh sách ──
    def _show_list(self):
        self._clear()
        ctk.CTkLabel(self._top, text="訳  Bản dịch", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=14, pady=10)
        e = ctk.CTkEntry(self._top, width=260, placeholder_text="Tìm trong tiếng Nhật, nghĩa, tiêu đề…"); e.pack(side="left", padx=8)
        if self._q:
            e.insert(0, self._q)
        e.bind("<KeyRelease>", lambda _x: (setattr(self, "_q", e.get()), self._debounce()))
        self.search_var = _EntryText(e)
        m = ctk.CTkOptionMenu(self._top, values=["Mọi cấp"] + list(JLPT_LEVELS), width=100, command=self._on_jlpt)
        m.set(self._jlpt or "Mọi cấp"); m.pack(side="left", padx=4)
        ctk.CTkButton(self._top, text="➕  Thêm", width=90, command=lambda: TranslationDialog(self.winfo_toplevel(), self._svc, self._after_save)).pack(side="right", padx=14, pady=9)
        lst = ctk.CTkScrollableFrame(self._body, corner_radius=0); lst.grid(row=0, column=0, sticky="nsew")
        self._lst = lst
        self._draw_list()

    def _debounce(self):
        if self._timer:
            self.after_cancel(self._timer)
        self._timer = self.after(200, self._draw_list)

    def _on_jlpt(self, v):
        self._jlpt = "" if v == "Mọi cấp" else v
        self._draw_list()

    def _draw_list(self):
        self._timer = None
        if not getattr(self, "_lst", None) or not self._lst.winfo_exists() or self._open:
            return
        for w in self._lst.winfo_children():
            w.destroy()
        items = self._svc.list_translations(self.search_var.get(), self._jlpt)
        if not items:
            ctk.CTkLabel(self._lst, text="Chưa có bản dịch nào.\nBấm “➕ Thêm” để dán một câu hoặc cả bài văn tiếng Nhật.",
                         justify="center", text_color=("gray40", "gray60")).pack(pady=60)
        for t in items:
            n = len(parse_glossary(t.get("glossary")))
            paras = len(split_paras(t["jp"]))
            head = (t.get("title") or _clip(t["jp"], 30)) + (f"   [{t['jlpt_level']}]" if t.get("jlpt_level") else "")
            sub = f"{len(t['jp'].replace(chr(10), ''))} chữ · {paras} đoạn" + (f" · {n} từ vựng" if n else "") + ("" if t.get("vi") else " · chưa có bản dịch")
            b = ctk.CTkButton(self._lst, anchor="w", height=64, corner_radius=8, fg_color=("gray88", "gray22"), hover_color=("gray78", "gray30"),
                              text_color=("gray10", "gray90"), font=ctk.CTkFont(family=JP_FONT, size=14),
                              text=f"{head}\n{_clip(t['jp'], 70)}\n{sub}", command=lambda i=t["id"]: self.open_item(i))
            b.pack(fill="x", padx=8, pady=3)

    def open_item(self, tid):
        self._open = tid
        self._show_reader()

    def _after_save(self, tid):
        if tid:
            self._open = tid
        self.refresh()

    # ── trang đọc ──
    def _show_reader(self):
        self._clear()
        t = self._svc.get_translation(self._open)
        if not t:
            return self._show_list()
        gl = parse_glossary(t.get("glossary"))
        jp, vi = split_paras(t["jp"]), split_paras(t.get("vi"))
        ctk.CTkButton(self._top, text="←", width=40, command=self._back).pack(side="left", padx=(10, 6), pady=9)
        ctk.CTkLabel(self._top, text=t.get("title") or _clip(t["jp"], 24), font=ctk.CTkFont(family=JP_FONT, size=15, weight="bold")).pack(side="left", padx=6)
        ctk.CTkLabel(self._top, text=f"{len(''.join(jp))} chữ · {len(jp)} đoạn" + (f" · {t['jlpt_level']}" if t.get("jlpt_level") else ""),
                     text_color=("gray40", "gray60")).pack(side="left", padx=8)
        ctk.CTkButton(self._top, text="✏️ Sửa", width=80, command=lambda: TranslationDialog(self.winfo_toplevel(), self._svc, self._after_save, t["id"])).pack(side="right", padx=14, pady=9)
        seg = ctk.CTkSegmentedButton(self._top, values=[m[1] for m in MODES], command=self._on_mode)
        seg.set(dict(MODES)[self._mode]); seg.pack(side="right", padx=8)

        c = _colors()
        main = ctk.CTkFrame(self._body, fg_color="transparent"); main.grid(row=0, column=0, sticky="nsew")
        main.grid_rowconfigure(0, weight=1); main.grid_columnconfigure(0, weight=3)
        two = self._mode == "two"
        if two:
            main.grid_columnconfigure(1, weight=2, minsize=300)
        left = ctk.CTkFrame(main, fg_color="transparent"); left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=10)
        left.grid_rowconfigure(0, weight=1); left.grid_columnconfigure(0, weight=1)
        txt = tk.Text(left, wrap="word", font=(JP_FONT, 15), bg=c["bg"], fg=c["fg"], relief="flat", padx=18, pady=14, spacing1=2, spacing2=6,
                      spacing3=14, insertwidth=0, cursor="xterm", highlightthickness=0)
        sb = tk.Scrollbar(left, command=txt.yview); txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew"); sb.grid(row=0, column=1, sticky="ns")
        self._txt = txt
        txt.tag_configure("gl", foreground=RED, underline=True)
        txt.tag_configure("vi", foreground=c["mute"], font=("Segoe UI", 12), spacing3=18)
        txt.tag_configure("cover", foreground=c["cover"], background=c["cover"])
        txt.tag_configure("warn", foreground=c["mute"], font=("Segoe UI", 10, "italic"))
        terms = [g["term"] for g in gl]

        def put_jp(i, text):
            start = txt.index("end-1c")
            txt.insert("end", text)
            end = txt.index("end-1c")
            txt.tag_add(f"p{i}", start, end)
            for a, b in find_spans(text, terms):
                txt.tag_add("gl", f"{start}+{a}c", f"{start}+{b}c")
            txt.insert("end", "\n")

        paired = bool(vi) and len(vi) == len(jp)
        if self._mode in ("two", "jp") or not vi:
            for i, p in enumerate(jp):
                put_jp(i, p)
        elif paired:
            for i, p in enumerate(jp):
                put_jp(i, p)
                self._put_vi(txt, i, vi[i])
        else:
            for i, p in enumerate(jp):
                put_jp(i, p)
            txt.insert("end", "\n")
            for i, p in enumerate(vi):
                self._put_vi(txt, i, p)
            txt.insert("end", f"\nSố đoạn tiếng Nhật ({len(jp)}) và tiếng Việt ({len(vi)}) khác nhau nên không ghép cặp.\n", "warn")
        txt.bind("<Key>", lambda e: None if e.state & 4 else "break")      # chỉ đọc nhưng vẫn chọn / Ctrl+C được
        txt.bind("<ButtonRelease-1>", lambda e: self.after(30, self._update_sel))
        txt.bind("<KeyRelease>", lambda e: self.after(30, self._update_sel))
        # thanh ghi nhanh dưới bài đọc
        self._selbar = ctk.CTkFrame(left, corner_radius=8, fg_color=("gray88", "gray22"))
        self._selbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._sel_lbl = ctk.CTkLabel(self._selbar, text="Bôi đen chữ trong bài để ghi nhanh từ mới", anchor="w", text_color=("gray40", "gray60"), font=ctk.CTkFont(family=JP_FONT, size=13))
        self._sel_lbl.pack(side="left", padx=12, pady=8)
        self._sel_btns = []
        for txt_, fn in (("＋ Ví dụ ngữ pháp", self._note_grammar), ("＋ Thẻ từ vựng", self._note_vocab), ("＋ Ghi vào từ vựng", self._note_gloss)):
            b = ctk.CTkButton(self._selbar, text=txt_, height=30, width=130, state="disabled", command=fn); b.pack(side="right", padx=4, pady=6); self._sel_btns.append(b)
        if two:
            self._side_panel(main, t, gl, vi)

    def _put_vi(self, txt, i, text):
        tag = f"v{i}"
        if self._mode == "hide":
            txt.tag_configure(tag, foreground=_colors()["cover"], background=_colors()["cover"], font=("Segoe UI", 12), spacing3=18)
            txt.tag_bind(tag, "<Button-1>", lambda e, tg=tag: txt.tag_configure(tg, foreground=_colors()["mute"], background=_colors()["bg"]))
            txt.tag_bind(tag, "<Enter>", lambda e: txt.configure(cursor="hand2")); txt.tag_bind(tag, "<Leave>", lambda e: txt.configure(cursor="xterm"))
            txt.insert("end", text + "\n", (tag,))
        else:
            txt.insert("end", text + "\n", ("vi",))

    def _side_panel(self, main, t, gl, vi):
        side = ctk.CTkFrame(main, corner_radius=10); side.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=10)
        side.grid_rowconfigure(1, weight=1); side.grid_columnconfigure(0, weight=1)
        seg = ctk.CTkSegmentedButton(side, values=[f"Từ vựng · {len(gl)}" if gl else "Từ vựng", "Bản dịch"], command=self._on_side)
        seg.set("Bản dịch" if self._side == "vi" else (f"Từ vựng · {len(gl)}" if gl else "Từ vựng")); seg.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        body = ctk.CTkScrollableFrame(side, fg_color="transparent"); body.grid(row=1, column=0, sticky="nsew", padx=4)
        if self._side == "vi":
            if not vi:
                ctk.CTkLabel(body, text="Chưa có bản dịch — bấm ✏️ Sửa để ghi nghĩa tiếng Việt.", wraplength=260, justify="left", text_color=("gray40", "gray60")).pack(padx=8, pady=8)
            for p in vi:
                ctk.CTkLabel(body, text=p, wraplength=270, justify="left", anchor="w").pack(fill="x", padx=8, pady=(0, 10))
            return
        if not gl:
            ctk.CTkLabel(body, text="Chưa có từ vựng. Bôi đen từ trong bài rồi bấm “＋ Ghi vào từ vựng”, hoặc bấm “+ Thêm từ”.", wraplength=260, justify="left",
                         text_color=("gray40", "gray60")).pack(padx=8, pady=8)
        for i, g in enumerate(gl):
            ctk.CTkButton(body, anchor="w", height=34, fg_color="transparent", hover_color=("gray85", "gray28"), text_color=("gray10", "gray95"),
                          text=f"{g['term']}  =  {g['meaning']}" if g["meaning"] else g["term"], font=ctk.CTkFont(family=JP_FONT, size=14),
                          command=lambda k=i: self._edit_gloss(k)).pack(fill="x", padx=4, pady=1)
        bar = ctk.CTkFrame(side, fg_color="transparent"); bar.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkButton(bar, text="+ Thêm từ", width=90, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=lambda: self._edit_gloss(None)).pack(side="left")
        if gl:
            ctk.CTkButton(bar, text="＋ Thêm vào bộ thẻ…", command=self._bulk).pack(side="right")

    # ── hành động ──
    def _back(self):
        self._open = None
        self._show_list()

    def _on_mode(self, label):
        self._mode = next(k for k, v in MODES if v == label)
        self._show_reader()

    def _on_side(self, label):
        self._side = "vi" if label == "Bản dịch" else "gloss"
        self._show_reader()

    def _edit_gloss(self, idx, preset=None):
        GlossDialog(self.winfo_toplevel(), self._svc, self._open, idx, preset, self._show_reader, self._gloss_to_card)

    def _bulk(self):
        t = self._svc.get_translation(self._open)
        recent = []
        try:
            from infrastructure import settings
            recent = list(settings.get("recent_decks", []) or [])
        except Exception:
            pass
        BulkCardsDialog(self.winfo_toplevel(), self._svc, t, self._decks.list_decks(), recent, self._after_bulk)

    def _after_bulk(self, deck_ids):
        try:
            from infrastructure import settings
            settings.set("recent_decks", list(deck_ids)[:6])
        except Exception:
            pass
        self._on_cards_changed()

    def _gloss_to_card(self, term, meaning):
        self._card_form(term, meaning)

    def _card_form(self, term, meaning=""):
        t = self._svc.get_translation(self._open)
        if self._svc.card_exists(term):
            return messagebox.showinfo("Đã có", f"“{term}” đã có trong thư viện.", parent=self.winfo_toplevel())
        preset = self._svc.card_preset(t, term, meaning)

        def save(data):
            self._cards.add(data)
            self._on_cards_changed()
        CardForm(self.winfo_toplevel(), self._cards, on_save=save, preset=preset)

    # ── chọn chữ trong bài ──
    def _read_selection(self):
        txt = self._txt
        try:
            a, b = txt.index("sel.first"), txt.index("sel.last")
        except tk.TclError:
            return None
        text = " ".join(txt.get(a, b).split())
        if not text or len(text) > 300:
            return None
        pi = next((int(n[1:]) for n in txt.tag_names(a) if n.startswith("p") and n[1:].isdigit()), None)
        if pi is None:
            return None
        t = self._svc.get_translation(self._open)
        jp, vis = split_paras(t["jp"]), split_paras(t.get("vi"))
        para = jp[pi]
        return {"text": text, "sentence": sentence_of(para, text), "paragraph": para,
                "vi": vis[pi] if len(vis) == len(jp) else "", "title": t.get("title") or para[:20], "id": t["id"]}

    def _update_sel(self):
        if not getattr(self, "_txt", None) or not self._txt.winfo_exists():
            return
        self._sel = self._read_selection()
        on = self._sel is not None
        for b in self._sel_btns:
            b.configure(state="normal" if on else "disabled")
        self._sel_lbl.configure(text=f"«{_clip(self._sel['text'], 22)}»" if on else "Bôi đen chữ trong bài để ghi nhanh từ mới",
                                text_color=("gray10", "gray95") if on else ("gray40", "gray60"))

    def _take(self):
        s = self._sel
        return s

    def _note_gloss(self):
        s = self._take()
        if s:
            self._side = "gloss"
            self._edit_gloss(None, s["text"])

    def _note_vocab(self):
        s = self._take()
        if s:
            self._card_form(s["text"])

    def _note_grammar(self):
        s = self._take()
        if s:
            GrammarPickDialog(self.winfo_toplevel(), self._svc, s, self._new_grammar)

    def _new_grammar(self, line):
        if self._grammar_view is not None:
            self._grammar_view.open_form(None, {"examples": line})
