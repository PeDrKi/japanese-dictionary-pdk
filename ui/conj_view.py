"""
ui/conj_view.py — màn "活 Chia động từ": bảng động từ (cột đầu: thể ます) × các thể khác.
Sửa từng ô ngay trên bảng; thêm / sửa / xóa / ẩn / đổi thứ tự cột; tự điền theo quy tắc chia (nhóm 1 / 2 / 3). Giống bản web.
"""
import logging
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from constants import KB_ESCAPE, KB_SAVE
from domain.conjugation import CONJ_KINDS, GRP_HINT, GRP_LABEL, KIND_INFO, conjugate, guess_group

logger = logging.getLogger(__name__)


class _EntryText:
    """Đọc nội dung ô tìm kiếm (CTkEntry có placeholder không dùng được textvariable)."""
    def __init__(self, entry):
        self._e = entry

    def get(self):
        return self._e.get()
JP_FONT = "Noto Sans JP"
GRP_COLOR = {1: "#E85D5D", 2: "#4ECB85", 3: "#9B7FE8", 0: "#888888"}


def _dark():
    return ctk.get_appearance_mode() == "Dark"


class VerbDialog(ctk.CTkToplevel):
    def __init__(self, master, service, on_done, vid=None, default_grp=0):
        super().__init__(master)
        self._svc, self._on_done, self._vid = service, on_done, vid
        v = next((x for x in service.verbs() if x["id"] == vid), None) if vid else None
        self.title("✏️  Sửa động từ" if vid else "➕  Thêm động từ")
        self.geometry("460x440"); self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy()); self.bind(KB_SAVE, lambda _: self._save())
        p = dict(padx=20, pady=(12, 2), anchor="w")
        ctk.CTkLabel(self, text="Thể ます *", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.masu_e = ctk.CTkEntry(self, font=ctk.CTkFont(family=JP_FONT, size=18), placeholder_text="たべます / 食べます")
        self.masu_e.pack(fill="x", padx=20); self.masu_e.insert(0, v["masu"] if v else "")
        ctk.CTkLabel(self, text="Nghĩa", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.mean_e = ctk.CTkEntry(self, placeholder_text="ăn"); self.mean_e.pack(fill="x", padx=20)
        self.mean_e.insert(0, (v or {}).get("meaning_vi") or "")
        ctk.CTkLabel(self, text="Nhóm *", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.grp_var = ctk.IntVar(value=(v or {}).get("grp") or default_grp or 0)
        for g in (1, 2, 3):
            ctk.CTkRadioButton(self, text=f"{GRP_LABEL[g]}   {GRP_HINT[g]}", variable=self.grp_var, value=g,
                               font=ctk.CTkFont(family=JP_FONT, size=12)).pack(anchor="w", padx=24, pady=2)
        self.fill_var = ctk.BooleanVar(value=True)
        if any(f["kind"] for f in service.forms()):
            ctk.CTkCheckBox(self, text="Điền các ô trống theo quy tắc chia", variable=self.fill_var).pack(anchor="w", padx=20, pady=(12, 0))
        if vid:
            ctk.CTkButton(self, text="Điền lại TOÀN BỘ các thể của động từ này (ghi đè)", fg_color="transparent", text_color=("#1F6AA5", "#6CB4EE"),
                          hover=False, anchor="w", command=self._refill).pack(anchor="w", padx=14)
        self.masu_e.bind("<KeyRelease>", lambda _: self._guess())
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(side="bottom", fill="x", padx=20, pady=14)
        ctk.CTkButton(bar, text="✕  Hủy", width=90, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=self.destroy).pack(side="left")
        if vid:
            ctk.CTkButton(bar, text="🗑  Xóa", width=80, fg_color="#c0392b", hover_color="#922b21", command=self._delete).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="💾  Lưu", height=36, command=self._save).pack(side="right")
        self.masu_e.focus_set()

    def _guess(self):
        if not self.grp_var.get():
            g = guess_group(self.masu_e.get())
            if g:
                self.grp_var.set(g)

    def _save(self):
        masu, grp = self.masu_e.get().strip(), self.grp_var.get()
        if not masu or grp not in (1, 2, 3):
            return messagebox.showwarning("Chưa lưu", "Cần nhập thể ます và chọn nhóm", parent=self)
        if self._svc.has_masu(masu, self._vid) and not messagebox.askyesno("Trùng", f'"{masu}" đã có trong bảng. Vẫn lưu thêm?', parent=self):
            return
        _, n = self._svc.save_verb(self._vid, masu, self.mean_e.get(), grp, fill=self.fill_var.get())
        if self.fill_var.get() and not n and not conjugate(masu, grp, "dict"):
            messagebox.showinfo("Lưu ý", "Không tự điền được: kiểm tra lại thể ます và nhóm.", parent=self)
        self._on_done(); self.destroy()

    def _refill(self):
        if messagebox.askyesno("Điền lại", "Các ô đã sửa tay của cột có quy tắc chia sẽ bị ghi đè. Tiếp tục?", parent=self):
            n = self._svc.fill(verb_ids=[self._vid], overwrite=True)
            messagebox.showinfo("Xong", f"Đã điền {n} ô", parent=self)
            self._on_done(); self.destroy()

    def _delete(self):
        if messagebox.askyesno("Xóa", "Xóa động từ này và các thể đã chia? Không thể hoàn tác.", parent=self):
            self._svc.delete_verb(self._vid); self._on_done(); self.destroy()


class FormDialog(ctk.CTkToplevel):
    def __init__(self, master, service, on_done, fid=None):
        super().__init__(master)
        self._svc, self._on_done, self._fid = service, on_done, fid
        f = next((x for x in service.forms() if x["id"] == fid), None) if fid else None
        self.title("✏️  Sửa cột" if fid else "➕  Thêm cột")
        self.geometry("460x360"); self.resizable(False, False)
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy()); self.bind(KB_SAVE, lambda _: self._save())
        p = dict(padx=20, pady=(12, 2), anchor="w")
        ctk.CTkLabel(self, text="Loại thể (để tự điền)", font=ctk.CTkFont(weight="bold")).pack(**p)
        self._labels = {"": "— Cột tự đặt (tự nhập nội dung) —", **{k[0]: f"{k[1]} — {k[2]}" for k in CONJ_KINDS}}
        self.kind_var = ctk.StringVar(value=self._labels.get((f or {}).get("kind") or "", self._labels[""]))
        ctk.CTkOptionMenu(self, values=list(self._labels.values()), variable=self.kind_var, command=self._on_kind).pack(fill="x", padx=20)
        ctk.CTkLabel(self, text="Tên cột *", font=ctk.CTkFont(weight="bold")).pack(**p)
        self.name_e = ctk.CTkEntry(self, font=ctk.CTkFont(family=JP_FONT, size=16)); self.name_e.pack(fill="x", padx=20)
        self.name_e.insert(0, (f or {}).get("name") or "")
        self.hidden_var = ctk.BooleanVar(value=bool((f or {}).get("hidden")))
        ctk.CTkCheckBox(self, text="Ẩn cột này khỏi bảng", variable=self.hidden_var).pack(anchor="w", padx=20, pady=(12, 0))
        self.fill_var = ctk.BooleanVar(value=not fid)
        if service.verbs():
            ctk.CTkCheckBox(self, text="Tự điền các ô trống của cột theo quy tắc chia", variable=self.fill_var).pack(anchor="w", padx=20, pady=(8, 0))
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(side="bottom", fill="x", padx=20, pady=14)
        ctk.CTkButton(bar, text="✕  Hủy", width=90, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=self.destroy).pack(side="left")
        if fid:
            ctk.CTkButton(bar, text="🗑  Xóa", width=80, fg_color="#c0392b", hover_color="#922b21", command=self._delete).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="💾  Lưu", height=36, command=self._save).pack(side="right")
        self.name_e.focus_set()

    def _kind(self):
        cur = self.kind_var.get()
        return next((k for k, v in self._labels.items() if v == cur), "")

    def _on_kind(self, _):
        k = self._kind()
        if k and not self.name_e.get().strip():
            self.name_e.insert(0, KIND_INFO[k][1])

    def _save(self):
        name, kind = self.name_e.get().strip(), self._kind()
        if not name:
            self.name_e.configure(border_color="red")
            return
        fid = self._svc.save_form(self._fid, name, kind, self.hidden_var.get())
        if self.fill_var.get() and kind:
            self._svc.fill(form_ids=[fid])
        self._on_done(); self.destroy()

    def _delete(self):
        if messagebox.askyesno("Xóa cột", "Xóa cột này cùng nội dung các ô? Không thể hoàn tác.\n(Muốn giữ lại thì chọn “Ẩn cột”.)", parent=self):
            self._svc.delete_form(self._fid); self._on_done(); self.destroy()


class ColumnsDialog(ctk.CTkToplevel):
    """Danh sách cột: ẩn/hiện, đổi thứ tự, sửa, thêm."""

    def __init__(self, master, service, on_done):
        super().__init__(master)
        self._svc, self._on_done = service, on_done
        self.title("Các cột của bảng"); self.geometry("460x520")
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self._close)
        ctk.CTkLabel(self, text="Cột đầu (thể ます) luôn hiện. 👁 ẩn / hiện · ▲ ▼ đổi thứ tự.", text_color=("gray40", "gray60")).pack(padx=16, pady=(12, 4), anchor="w")
        self.body = ctk.CTkScrollableFrame(self); self.body.pack(fill="both", expand=True, padx=10)
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(bar, text="Thêm thể thông dụng", command=self._defaults).pack(side="left")
        ctk.CTkButton(bar, text="＋ Cột mới", command=lambda: FormDialog(self, service, self._draw)).pack(side="right")
        self._draw()

    def _close(self):
        self._on_done(); self.destroy()

    def _defaults(self):
        ids = self._svc.add_default_forms()
        if ids and self._svc.verbs():
            self._svc.fill(form_ids=ids)
        self._draw()

    def _draw(self):
        for w in self.body.winfo_children():
            w.destroy()
        fs = self._svc.forms()
        for i, f in enumerate(fs):
            row = ctk.CTkFrame(self.body, corner_radius=8); row.pack(fill="x", pady=2)
            ctk.CTkButton(row, text="🙈" if f["hidden"] else "👁", width=34, fg_color="transparent", hover_color=("gray80", "gray30"),
                          command=lambda x=f: (self._svc.toggle_form(x["id"], not x["hidden"]), self._draw())).pack(side="left", padx=4, pady=4)
            info = KIND_INFO.get(f["kind"])
            ctk.CTkLabel(row, text=f["name"] + ("   (đang ẩn)" if f["hidden"] else ""), anchor="w",
                         text_color=("gray50", "gray55") if f["hidden"] else ("gray10", "gray95"),
                         font=ctk.CTkFont(family=JP_FONT, size=14)).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=info[2] if info else "Cột tự đặt", text_color=("gray45", "gray60"), font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
            ctk.CTkButton(row, text="✏️", width=32, fg_color="transparent", hover_color=("gray80", "gray30"),
                          command=lambda x=f: FormDialog(self, self._svc, self._draw, x["id"])).pack(side="right", padx=2)
            for txt, d, ok in (("▼", 1, i < len(fs) - 1), ("▲", -1, i > 0)):
                ctk.CTkButton(row, text=txt, width=30, fg_color="transparent", hover_color=("gray80", "gray30"),
                              state="normal" if ok else "disabled",
                              command=lambda x=f, dd=d: (self._svc.move_form(x["id"], dd), self._draw())).pack(side="right")
        if not fs:
            ctk.CTkLabel(self.body, text="Chưa có cột nào.").pack(pady=30)


class ImportDialog(ctk.CTkToplevel):
    def __init__(self, master, service, cands, on_done):
        super().__init__(master)
        self._svc, self._cands, self._on_done = service, cands, on_done
        self.title("Lấy từ thẻ động từ"); self.geometry("460x520")
        self.grab_set(); self.lift(); self.focus_force()
        self.bind(KB_ESCAPE, lambda _: self.destroy())
        ctk.CTkLabel(self, text=f"{len(cands)} thẻ động từ chưa có trong bảng. Bỏ tích những từ không muốn thêm.",
                     wraplength=420, justify="left").pack(padx=16, pady=(12, 4), anchor="w")
        body = ctk.CTkScrollableFrame(self); body.pack(fill="both", expand=True, padx=10)
        self._vars = []
        for c in cands:
            v = ctk.BooleanVar(value=True); self._vars.append(v)
            ctk.CTkCheckBox(body, variable=v, font=ctk.CTkFont(family=JP_FONT, size=14),
                            text=f"{c['masu']}  (nhóm {c['grp']})  {c['card'].get('meaning_vi') or ''}").pack(anchor="w", pady=3, padx=6)
        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(bar, text="Hủy", width=80, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=self.destroy).pack(side="left")
        ctk.CTkButton(bar, text="Thêm vào bảng", command=self._ok).pack(side="right")

    def _ok(self):
        pick = [c for c, v in zip(self._cands, self._vars) if v.get()]
        if pick:
            self._svc.import_candidates(pick)
            self._on_done()
        self.destroy()


class ConjView(ctk.CTkFrame):
    def __init__(self, master, material_service):
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self._svc = material_service
        self._grp = ""
        self._entries = {}          # (verb_id, form_id) → tk.Entry
        self._orig = {}
        self.grid_rowconfigure(2, weight=1); self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray90", "gray18"), height=50)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(top, text="活  Chia động từ", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=14, pady=10)
        _e = ctk.CTkEntry(top, width=240, placeholder_text="Tìm động từ, nghĩa hoặc thể đã chia…")
        _e.pack(side="left", padx=8)
        _e.bind("<KeyRelease>", lambda _x: self._debounce())
        self.search_var = _EntryText(_e)
        ctk.CTkButton(top, text="➕  Động từ", width=100, command=lambda: VerbDialog(self.winfo_toplevel(), self._svc, self.refresh, default_grp=int(self._grp or 0))).pack(side="right", padx=14, pady=9)
        self.count_lbl = ctk.CTkLabel(top, text="", text_color=("gray40", "gray60")); self.count_lbl.pack(side="right", padx=8)

        bar = ctk.CTkFrame(self, fg_color="transparent"); bar.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        self.grp_seg = ctk.CTkSegmentedButton(bar, values=["Tất cả", "Nhóm 1", "Nhóm 2", "Nhóm 3"], command=self._on_grp)
        self.grp_seg.set("Tất cả"); self.grp_seg.pack(side="left")
        for txt, fn in (("Cột…", self._columns), ("Lấy từ thẻ", self._import), ("Tự điền ô trống", self._fill_all)):
            ctk.CTkButton(bar, text=txt, width=110, height=28, fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"), command=fn).pack(side="left", padx=(8, 0))

        wrap = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent"); wrap.grid(row=2, column=0, sticky="nsew")
        wrap.grid_rowconfigure(0, weight=1); wrap.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(wrap, highlightthickness=0, bd=0)
        vs = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview); hs = tk.Scrollbar(wrap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.canvas.grid(row=0, column=0, sticky="nsew"); vs.grid(row=0, column=1, sticky="ns"); hs.grid(row=1, column=0, sticky="ew")
        self.inner = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120 or (1 if e.delta > 0 else -1)), "units"))
        self._timer = None
        self.refresh()

    def _debounce(self):
        if self._timer:
            self.after_cancel(self._timer)
        self._timer = self.after(200, self.refresh)

    def _on_grp(self, v):
        self._grp = {"Tất cả": "", "Nhóm 1": "1", "Nhóm 2": "2", "Nhóm 3": "3"}[v]
        self.refresh()

    def _columns(self):
        ColumnsDialog(self.winfo_toplevel(), self._svc, self.refresh)

    def _import(self):
        cands = self._svc.candidates()
        if not cands:
            return messagebox.showinfo("Lấy từ thẻ", "Không có thẻ động từ mới.\n(Thẻ cần có từ loại Động từ nhóm 1 / 2 / 3.)", parent=self.winfo_toplevel())
        ImportDialog(self.winfo_toplevel(), self._svc, cands, self.refresh)

    def _fill_all(self):
        if not self._svc.verbs() or not any(f["kind"] for f in self._svc.forms()):
            return messagebox.showinfo("Tự điền", "Cần có động từ và cột có loại thể để tự điền.", parent=self.winfo_toplevel())
        n = self._svc.fill()
        messagebox.showinfo("Tự điền", f"Đã điền {n} ô trống" if n else "Không còn ô nào cần điền.", parent=self.winfo_toplevel())
        self.refresh()

    # ── vẽ bảng ──
    def refresh(self, force=None):
        self._timer = None
        forms_all = self._svc.forms(); forms = [f for f in forms_all if not f["hidden"]]
        verbs_all = self._svc.verbs(); cells = self._svc.cells()
        vs = [v for v in verbs_all if not self._grp or str(v["grp"]) == self._grp]
        q = self.search_var.get().strip().lower()
        if q:
            vs = [v for v in vs if q in (v["masu"] + " " + (v["meaning_vi"] or "") + " " + " ".join(cells.get((v["id"], f["id"]), "") for f in forms_all)).lower()]
        yv = self.canvas.yview(); xv = self.canvas.xview()
        for w in self.inner.winfo_children():
            w.destroy()
        self._entries.clear(); self._orig.clear()
        hidden = len(forms_all) - len(forms)
        self.count_lbl.configure(text=f"{len(vs)}" + (f"/{len(verbs_all)}" if len(vs) != len(verbs_all) else "") + f" động từ · {len(forms)} cột" + (f" · {hidden} ẩn" if hidden else ""))
        dark = _dark()
        bg, fg, hd = ("#1e2130", "#e8eaf0", "#2a2f45") if dark else ("#ffffff", "#1a1a2e", "#e4e7ef")
        self.canvas.configure(bg=bg); self.inner.configure(bg=bg)
        if not forms_all:
            tk.Label(self.inner, bg=bg, fg=fg, font=("Segoe UI", 12), justify="left",
                     text="Chưa có cột nào.\nBấm “Cột…” → “Thêm thể thông dụng” để tạo sẵn 辞書形, ない形, て形, た形, 可能形…").grid(padx=30, pady=30)
            return
        tk.Label(self.inner, text="ます形", bg=hd, fg=fg, font=("Noto Sans JP", 11, "bold"), width=18, pady=8).grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        for c, f in enumerate(forms, 1):
            b = tk.Label(self.inner, text=f["name"], bg=hd, fg=fg, font=("Noto Sans JP", 11, "bold"), width=14, pady=8, cursor="hand2")
            b.grid(row=0, column=c, sticky="nsew", padx=1, pady=1)
            b.bind("<Button-1>", lambda e, x=f["id"]: FormDialog(self.winfo_toplevel(), self._svc, self.refresh, x))
        for r, v in enumerate(vs, 1):
            lab = tk.Label(self.inner, text=f"{v['masu']}   {v['grp'] or '?'}" + (f"\n{v['meaning_vi']}" if v["meaning_vi"] else ""), bg=bg, fg=GRP_COLOR.get(v["grp"] or 0),
                           font=("Noto Sans JP", 11, "bold"), anchor="w", justify="left", width=18, cursor="hand2", padx=6)
            lab.grid(row=r, column=0, sticky="nsew", padx=1, pady=1)
            lab.bind("<Button-1>", lambda e, x=v["id"]: VerbDialog(self.winfo_toplevel(), self._svc, self.refresh, x))
            for c, f in enumerate(forms, 1):
                key = (v["id"], f["id"]); val = cells.get(key, "")
                e = tk.Entry(self.inner, font=("Noto Sans JP", 12), width=14, bg=bg, fg=fg, insertbackground=fg, relief="solid", bd=1, highlightthickness=1,
                             highlightbackground=hd, highlightcolor="#3B8ED0")
                e.insert(0, val); e.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)
                self._entries[key] = e; self._orig[key] = val
                e.bind("<FocusOut>", lambda ev, k=key: self._commit(k))
                e.bind("<Return>", lambda ev, k=key: self._enter(k))
                e.bind("<Escape>", lambda ev, k=key: self._revert(k))
        if not vs:
            tk.Label(self.inner, bg=bg, fg=fg, text="Không có động từ khớp." if verbs_all else "Chưa có động từ. Bấm “➕ Động từ” hoặc “Lấy từ thẻ”.",
                     font=("Segoe UI", 11)).grid(row=len(vs) + 1, column=0, columnspan=max(2, len(forms) + 1), pady=20, sticky="w", padx=10)
        self.update_idletasks()
        self.canvas.yview_moveto(yv[0]); self.canvas.xview_moveto(xv[0])

    def _commit(self, key):
        e = self._entries.get(key)
        if e is None:
            return
        val = e.get().strip()
        if val == self._orig.get(key, ""):
            return
        try:
            self._svc.set_cell(key[0], key[1], val)
            self._orig[key] = val
        except Exception as ex:
            logger.warning("Lưu ô lỗi: %s", ex)
            e.delete(0, "end"); e.insert(0, self._orig.get(key, ""))

    def _revert(self, key):
        e = self._entries.get(key)
        if e is not None:
            e.delete(0, "end"); e.insert(0, self._orig.get(key, ""))
            self.canvas.focus_set()

    def _enter(self, key):
        self._commit(key)
        order = list(self._entries)
        col = [k for k in order if k[1] == key[1]]
        i = col.index(key)
        (self._entries[col[i + 1]].focus_set() if i + 1 < len(col) else self.canvas.focus_set())
        return "break"
