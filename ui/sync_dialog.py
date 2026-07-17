"""
sync_dialog.py — Dialog sync Google Drive (OAuth2).
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os

from infrastructure.settings import get as settings_get, set as settings_set
from infrastructure.drive_sync import DriveSync, DEFAULT_DRIVE_FILENAME, TOKEN_PATH

_KEY_SECRET_PATH = "drive_client_secret_path"
_KEY_FOLDER_ID   = "drive_folder_id"
_KEY_FILENAME    = "drive_db_filename"


class SyncDialog(ctk.CTkToplevel):

    def __init__(self, master, on_sync_done=None):
        super().__init__(master)
        self.on_sync_done = on_sync_done
        self.title("☁️  Sync Google Drive")
        self.geometry("540x580")
        self.resizable(False, True)
        self.grab_set()
        self.lift()
        self.focus_force()
        self._syncing = False
        self._build()
        self._load_saved_settings()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=("gray88", "gray18"),
                           corner_radius=0, height=56)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        ctk.CTkLabel(
            hdr, text="☁️  Sync 2 chiều với Google Drive",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
        ).pack(side="left", padx=16, pady=14)

        # ── Config ──
        cfg = ctk.CTkFrame(self, fg_color=("gray90", "gray20"), corner_radius=10)
        cfg.grid(row=1, column=0, sticky="ew", padx=16, pady=(14, 0))
        cfg.grid_columnconfigure(0, weight=1)

        # Client Secret JSON
        ctk.CTkLabel(
            cfg, text="🔑  OAuth2 Client Secret JSON",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).grid(row=0, column=0, padx=14, pady=(14, 2), sticky="w")

        key_row = ctk.CTkFrame(cfg, fg_color="transparent")
        key_row.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        key_row.grid_columnconfigure(0, weight=1)

        self._secret_var = ctk.StringVar()
        ctk.CTkEntry(
            key_row, textvariable=self._secret_var,
            placeholder_text="Đường dẫn tới client_secret_xxx.json ...",
            height=32
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            key_row, text="📂", width=36, height=32,
            fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
            command=self._pick_secret_file
        ).grid(row=0, column=1, padx=(6, 0))

        # Folder ID (optional)
        ctk.CTkLabel(
            cfg, text="📁  Folder ID trên Drive  (để trống = root My Drive)",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).grid(row=2, column=0, padx=14, pady=(4, 2), sticky="w")

        self._folder_var = ctk.StringVar()
        ctk.CTkEntry(
            cfg, textvariable=self._folder_var,
            placeholder_text="VD: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs",
            height=32
        ).grid(row=3, column=0, padx=14, pady=(0, 8), sticky="ew")

        # Tên file
        ctk.CTkLabel(
            cfg, text="💾  Tên file trên Drive",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).grid(row=4, column=0, padx=14, pady=(4, 2), sticky="w")

        self._filename_var = ctk.StringVar(value=DEFAULT_DRIVE_FILENAME)
        ctk.CTkEntry(
            cfg, textvariable=self._filename_var, height=32
        ).grid(row=5, column=0, padx=14, pady=(0, 14), sticky="ew")

        # ── Token status ──
        self._token_frame = ctk.CTkFrame(
            self, fg_color=("gray88", "gray22"), corner_radius=8)
        self._token_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        self._token_frame.grid_columnconfigure(0, weight=1)

        self._token_label = ctk.CTkLabel(
            self._token_frame, text="",
            font=ctk.CTkFont(size=11), anchor="w",
            text_color=("gray40", "gray65")
        )
        self._token_label.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        self._revoke_btn = ctk.CTkButton(
            self._token_frame, text="🚪  Đăng xuất",
            height=26, width=110,
            fg_color=("gray70", "gray40"),
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=11),
            command=self._revoke_token
        )
        self._revoke_btn.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
        self._update_token_status()

        # ── Info ──
        info = ctk.CTkFrame(self, fg_color=("gray88", "gray22"), corner_radius=8)
        info.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 0))
        ctk.CTkLabel(
            info,
            text=(
                "ℹ️  Cách lấy Client Secret:\n"
                "  1. console.cloud.google.com → APIs & Services → Credentials\n"
                "  2. Create Credentials → OAuth Client ID → Desktop app\n"
                "  3. Download JSON → chọn file đó ở trên\n"
                "  4. Lần đầu sync: browser sẽ mở để đăng nhập Google"
            ),
            font=ctk.CTkFont(size=10),
            text_color=("gray45", "gray60"),
            justify="left", anchor="w"
        ).pack(fill="x", padx=12, pady=8)

        # ── Log ──
        ctk.CTkLabel(
            self, text="📋  Log",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray50", "gray55"), anchor="w"
        ).grid(row=4, column=0, sticky="w", padx=18, pady=(12, 2))

        self._log_box = ctk.CTkTextbox(
            self, height=120,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled", corner_radius=6
        )
        self._log_box.grid(row=5, column=0, sticky="nsew", padx=16, pady=(0, 6))

        # ── Buttons ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=6, column=0, sticky="ew", padx=16, pady=(0, 16))

        ctk.CTkButton(
            btn_row, text="✕  Đóng", width=100, height=38,
            fg_color=("gray75", "gray35"), text_color=("gray10", "gray90"),
            command=self._on_close
        ).pack(side="left")

        self._sync_btn = ctk.CTkButton(
            btn_row, text="☁️  Bắt đầu Sync", height=38,
            command=self._start_sync
        )
        self._sync_btn.pack(side="right")

    # ── Token status ──────────────────────────────────────────────────────────

    def _update_token_status(self):
        if os.path.exists(TOKEN_PATH):
            self._token_label.configure(
                text="✅  Đã đăng nhập — token được lưu tại:\n    " + TOKEN_PATH,
                text_color=("gray35", "#4ECB85")
            )
            self._revoke_btn.configure(state="normal")
        else:
            self._token_label.configure(
                text="⚪  Chưa đăng nhập — browser sẽ mở khi bạn nhấn Sync.",
                text_color=("gray45", "gray60")
            )
            self._revoke_btn.configure(state="disabled")

    def _revoke_token(self):
        if messagebox.askyesno(
            "Đăng xuất",
            "Xoá token đăng nhập?\nLần sync tiếp theo sẽ cần đăng nhập lại.",
            parent=self
        ):
            if os.path.exists(TOKEN_PATH):
                os.remove(TOKEN_PATH)
            self._update_token_status()
            self._append_log("🚪 Đã đăng xuất — token bị xoá.")

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_saved_settings(self):
        self._secret_var.set(settings_get(_KEY_SECRET_PATH, ""))
        self._folder_var.set(settings_get(_KEY_FOLDER_ID, ""))
        self._filename_var.set(
            settings_get(_KEY_FILENAME, DEFAULT_DRIVE_FILENAME))

    def _save_settings(self):
        settings_set(_KEY_SECRET_PATH, self._secret_var.get().strip())
        settings_set(_KEY_FOLDER_ID,   self._folder_var.get().strip())
        settings_set(_KEY_FILENAME,
                     self._filename_var.get().strip() or DEFAULT_DRIVE_FILENAME)

    # ── File picker ───────────────────────────────────────────────────────────

    def _pick_secret_file(self):
        path = filedialog.askopenfilename(
            title="Chọn OAuth2 Client Secret JSON",
            filetypes=[("JSON", "*.json"), ("All", "*.*")]
        )
        if path:
            self._secret_var.set(path)

    # ── Sync ──────────────────────────────────────────────────────────────────

    def _start_sync(self):
        if self._syncing:
            return

        secret_path = self._secret_var.get().strip()
        if not secret_path:
            messagebox.showwarning(
                "Thiếu thông tin",
                "Vui lòng chọn file OAuth2 Client Secret JSON.",
                parent=self)
            return
        if not os.path.isfile(secret_path):
            messagebox.showerror(
                "File không tồn tại", f"Không tìm thấy:\n{secret_path}",
                parent=self)
            return

        self._save_settings()
        self._clear_log()
        self._set_syncing(True)

        folder_id = self._folder_var.get().strip() or None
        filename  = self._filename_var.get().strip() or DEFAULT_DRIVE_FILENAME

        def _run():
            syncer = DriveSync(
                client_secret_path=secret_path,
                drive_filename=filename,
                drive_folder_id=folder_id,
                progress_cb=self._append_log_safe
            )
            ok, stats, err = syncer.sync()
            self.after(0, lambda: self._on_finished(ok, stats, err))

        threading.Thread(target=_run, daemon=True).start()

    def _on_finished(self, ok, stats, err):
        self._set_syncing(False)
        self._update_token_status()
        if ok:
            self._append_log(
                f"\n📊 Kết quả:\n"
                f"  ↑ Đẩy lên Drive    : {stats.get('pushed', 0)} thẻ\n"
                f"  ↓ Kéo về local     : {stats.get('pulled', 0)} thẻ\n"
                f"  🔀 Conflict đã giải : {stats.get('conflicts_resolved', 0)}\n"
                f"  — Bỏ qua (giống)   : {stats.get('skipped', 0)}"
            )
            if self.on_sync_done:
                self.on_sync_done()
        else:
            self._append_log(f"\n❌ Lỗi:\n{err}")
            messagebox.showerror("Sync thất bại", err, parent=self)

    # ── Log ───────────────────────────────────────────────────────────────────

    def _append_log(self, msg):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _append_log_safe(self, msg):
        if self.winfo_exists():
            self.after(0, lambda m=msg: self._append_log(m))

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ── State ─────────────────────────────────────────────────────────────────

    def _set_syncing(self, syncing):
        self._syncing = syncing
        if syncing:
            self._sync_btn.configure(
                text="⏳  Đang sync...", state="disabled",
                fg_color=("gray60", "gray40"))
        else:
            self._sync_btn.configure(
                text="☁️  Bắt đầu Sync", state="normal",
                fg_color=("#3B82F6", "#2563EB"))

    def _on_close(self):
        if self._syncing:
            if not messagebox.askyesno(
                    "Đang sync", "Sync chưa hoàn tất. Vẫn muốn đóng?",
                    parent=self):
                return
        self.destroy()
