"""
backup_view.py — Backup and restore dialog.
Accessible from the app navbar.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from infrastructure.backup import create_backup, restore_backup, list_backups
import os
import logging

logger = logging.getLogger(__name__)


class BackupView(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("💾  Sao lưu & Khôi phục")
        self.geometry("540x520")
        self.resizable(False, True)
        self.lift(); self.focus_force()
        self._backup_dir = os.path.expanduser("~")
        self._build()
        self._refresh_list()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Section: Create backup ──
        sec1 = ctk.CTkFrame(self, fg_color=("gray88","gray20"), corner_radius=10)
        sec1.grid(row=0, column=0, sticky="ew", padx=20, pady=(20,8))

        ctk.CTkLabel(sec1, text="💾  Tạo sao lưu",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(14,4))
        ctk.CTkLabel(sec1,
                     text="Sao lưu database + settings vào file .zip",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55"),
                     anchor="w").pack(fill="x", padx=16, pady=(0,10))

        dir_row = ctk.CTkFrame(sec1, fg_color="transparent")
        dir_row.pack(fill="x", padx=16, pady=(0,10))
        dir_row.grid_columnconfigure(0, weight=1)

        self._dir_lbl = ctk.CTkLabel(dir_row,
                                      text=self._backup_dir,
                                      font=ctk.CTkFont(size=11),
                                      text_color=("gray50","gray55"),
                                      anchor="w")
        self._dir_lbl.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(dir_row, text="📂 Chọn thư mục", width=130, height=30,
                      corner_radius=6,
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self._pick_dir
                      ).grid(row=0, column=1, padx=(8,0))

        ctk.CTkButton(sec1, text="💾  Tạo sao lưu ngay", height=38,
                      command=self._do_backup
                      ).pack(fill="x", padx=16, pady=(0,14))

        # ── Section: Restore ──
        sec2 = ctk.CTkFrame(self, fg_color=("gray88","gray20"), corner_radius=10)
        sec2.grid(row=1, column=0, sticky="ew", padx=20, pady=8)

        ctk.CTkLabel(sec2, text="♻️  Khôi phục",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(14,4))
        ctk.CTkLabel(sec2,
                     text="Chọn file .zip để khôi phục  (DB hiện tại sẽ được backup trước)",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray50","gray55"),
                     anchor="w").pack(fill="x", padx=16, pady=(0,10))
        ctk.CTkButton(sec2, text="📂  Chọn file .zip để khôi phục",
                      height=38,
                      fg_color=("#c0392b","#922b21"), text_color="white",
                      hover_color=("#922b21","#7b241c"),
                      command=self._do_restore
                      ).pack(fill="x", padx=16, pady=(0,14))

        # ── Section: Recent backups ──
        sec3 = ctk.CTkFrame(self, fg_color=("gray88","gray20"), corner_radius=10)
        sec3.grid(row=2, column=0, sticky="nsew", padx=20, pady=(8,20))
        sec3.grid_rowconfigure(1, weight=1)
        sec3.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(sec3, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(14,6))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="📋  Sao lưu gần đây",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(hdr, text="🔄", width=32, height=28,
                      fg_color=("gray75","gray35"), text_color=("gray10","gray90"),
                      command=self._refresh_list
                      ).grid(row=0, column=1)

        self._list_frame = ctk.CTkScrollableFrame(sec3, fg_color="transparent")
        self._list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0,12))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _pick_dir(self):
        d = filedialog.askdirectory(title="Chọn thư mục lưu backup",
                                     initialdir=self._backup_dir)
        if d:
            self._backup_dir = d
            self._dir_lbl.configure(text=d)
            self._refresh_list()

    def _do_backup(self):
        path, err = create_backup(self._backup_dir)
        if err:
            messagebox.showerror("Lỗi", err, parent=self)
        else:
            fname = os.path.basename(path)
            size  = os.path.getsize(path) // 1024
            messagebox.showinfo("Sao lưu thành công",
                                f"✅ Đã lưu:\n{fname}\n({size} KB)",
                                parent=self)
            self._refresh_list()

    def _do_restore(self):
        path = filedialog.askopenfilename(
            title="Chọn file backup .zip",
            initialdir=self._backup_dir,
            filetypes=[("Backup files","*.zip"),("All","*.*")])
        if not path:
            return
        if not messagebox.askyesno(
                "Xác nhận khôi phục",
                f"Khôi phục từ:\n{os.path.basename(path)}\n\n"
                f"⚠️  Database hiện tại sẽ bị thay thế!\n"
                f"(Sẽ có backup an toàn tự động)\n\n"
                f"Bạn chắc chắn?",
                parent=self):
            return
        ok, msg = restore_backup(path)
        if ok:
            messagebox.showinfo("Khôi phục thành công", msg, parent=self)
        else:
            messagebox.showerror("Lỗi", msg, parent=self)

    def _refresh_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        backups = list_backups(self._backup_dir)
        if not backups:
            ctk.CTkLabel(self._list_frame,
                         text="Chưa có file backup nào trong thư mục này",
                         text_color=("gray55","gray50"),
                         font=ctk.CTkFont(size=11)).pack(pady=16)
            return
        for b in backups:
            row = ctk.CTkFrame(self._list_frame,
                               fg_color=("gray82","gray25"), corner_radius=8)
            row.pack(fill="x", pady=3, padx=4)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row,
                         text=f"📦  {b['filename']}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         anchor="w").grid(row=0, column=0, padx=12, pady=(8,2), sticky="w")
            ctk.CTkLabel(row,
                         text=f"{b['mtime']}  ·  {b['size_kb']} KB",
                         font=ctk.CTkFont(size=10),
                         text_color=("gray50","gray55"),
                         anchor="w").grid(row=1, column=0, padx=12, pady=(0,8), sticky="w")
            ctk.CTkButton(row, text="Khôi phục", width=80, height=26,
                          corner_radius=6,
                          fg_color=("#c0392b","#922b21"), text_color="white",
                          hover_color=("#922b21","#7b241c"),
                          command=lambda p=b["path"]: self._restore_from(p)
                          ).grid(row=0, column=1, rowspan=2, padx=12, pady=8)

    def _restore_from(self, path: str):
        if not messagebox.askyesno(
                "Xác nhận",
                f"Khôi phục từ:\n{os.path.basename(path)}?\n\n"
                f"Database hiện tại sẽ bị thay thế.",
                parent=self):
            return
        ok, msg = restore_backup(path)
        if ok:
            messagebox.showinfo("Thành công", msg, parent=self)
        else:
            messagebox.showerror("Lỗi", msg, parent=self)
