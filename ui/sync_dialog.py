"""
sync_dialog.py — Dialog sync Supabase Storage (thay cho Google Drive OAuth).
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading

from infrastructure.settings import get as settings_get, set as settings_set
from infrastructure.supabase_sync import SupabaseSync, DEFAULT_BUCKET, DEFAULT_FILENAME

_KEY_URL      = "supabase_url"
_KEY_KEY      = "supabase_key"
_KEY_BUCKET   = "supabase_bucket"
_KEY_FILENAME = "supabase_db_filename"


class SyncDialog(ctk.CTkToplevel):

    def __init__(self, master, on_sync_done=None):
        super().__init__(master)
        self.on_sync_done = on_sync_done
        self.title("☁️  Sync Supabase")
        self.geometry("540x560")
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
            hdr, text="☁️  Sync 2 chiều với Supabase",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
        ).pack(side="left", padx=16, pady=14)

        # ── Config ──
        cfg = ctk.CTkFrame(self, fg_color=("gray90", "gray20"), corner_radius=10)
        cfg.grid(row=1, column=0, sticky="ew", padx=16, pady=(14, 0))
        cfg.grid_columnconfigure(0, weight=1)

        # Project URL
        ctk.CTkLabel(
            cfg, text="🌐  Project URL",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).grid(row=0, column=0, padx=14, pady=(14, 2), sticky="w")

        self._url_var = ctk.StringVar()
        ctk.CTkEntry(
            cfg, textvariable=self._url_var,
            placeholder_text="https://xxxxxxxx.supabase.co",
            height=32
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")

        # API Key
        ctk.CTkLabel(
            cfg, text="🔑  API Key  (anon hoặc service_role)",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).grid(row=2, column=0, padx=14, pady=(4, 2), sticky="w")

        self._key_var = ctk.StringVar()
        ctk.CTkEntry(
            cfg, textvariable=self._key_var,
            placeholder_text="eyJhbGciOi...",
            show="•",
            height=32
        ).grid(row=3, column=0, padx=14, pady=(0, 8), sticky="ew")

        # Bucket
        ctk.CTkLabel(
            cfg, text="🪣  Bucket Storage",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).grid(row=4, column=0, padx=14, pady=(4, 2), sticky="w")

        self._bucket_var = ctk.StringVar(value=DEFAULT_BUCKET)
        ctk.CTkEntry(
            cfg, textvariable=self._bucket_var, height=32
        ).grid(row=5, column=0, padx=14, pady=(0, 8), sticky="ew")

        # Tên file
        ctk.CTkLabel(
            cfg, text="💾  Tên file trong bucket",
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
        ).grid(row=6, column=0, padx=14, pady=(4, 2), sticky="w")

        self._filename_var = ctk.StringVar(value=DEFAULT_FILENAME)
        ctk.CTkEntry(
            cfg, textvariable=self._filename_var, height=32
        ).grid(row=7, column=0, padx=14, pady=(0, 14), sticky="ew")

        # ── Info ──
        info = ctk.CTkFrame(self, fg_color=("gray88", "gray22"), corner_radius=8)
        info.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        ctk.CTkLabel(
            info,
            text=(
                "ℹ️  Thiết lập 1 lần trên Supabase:\n"
                "  1. supabase.com → tạo project (miễn phí)\n"
                "  2. Storage → New bucket → đặt tên (vd: japanese-db-sync)\n"
                "  3. Settings → API → copy Project URL và API key\n"
                "  4. Dán vào 2 ô ở trên rồi bấm Bắt đầu Sync\n"
                "  Không cần đăng nhập browser — chỉ cần URL + key."
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
        ).grid(row=3, column=0, sticky="w", padx=18, pady=(12, 2))

        self._log_box = ctk.CTkTextbox(
            self, height=140,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled", corner_radius=6
        )
        self._log_box.grid(row=4, column=0, sticky="nsew", padx=16, pady=(0, 6))

        # ── Buttons ──
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 16))

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

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_saved_settings(self):
        self._url_var.set(settings_get(_KEY_URL, ""))
        self._key_var.set(settings_get(_KEY_KEY, ""))
        self._bucket_var.set(settings_get(_KEY_BUCKET, DEFAULT_BUCKET))
        self._filename_var.set(settings_get(_KEY_FILENAME, DEFAULT_FILENAME))

    def _save_settings(self):
        settings_set(_KEY_URL, self._url_var.get().strip())
        settings_set(_KEY_KEY, self._key_var.get().strip())
        settings_set(_KEY_BUCKET, self._bucket_var.get().strip() or DEFAULT_BUCKET)
        settings_set(_KEY_FILENAME,
                     self._filename_var.get().strip() or DEFAULT_FILENAME)

    # ── Sync ──────────────────────────────────────────────────────────────────

    def _start_sync(self):
        if self._syncing:
            return

        url = self._url_var.get().strip()
        key = self._key_var.get().strip()
        if not url or not key:
            messagebox.showwarning(
                "Thiếu thông tin",
                "Vui lòng nhập Project URL và API Key của Supabase.",
                parent=self)
            return

        self._save_settings()
        self._clear_log()
        self._set_syncing(True)

        bucket   = self._bucket_var.get().strip() or DEFAULT_BUCKET
        filename = self._filename_var.get().strip() or DEFAULT_FILENAME

        def _run():
            syncer = SupabaseSync(
                supabase_url=url,
                supabase_key=key,
                bucket=bucket,
                remote_filename=filename,
                progress_cb=self._append_log_safe
            )
            ok, stats, err = syncer.sync()
            self.after(0, lambda: self._on_finished(ok, stats, err))

        threading.Thread(target=_run, daemon=True).start()

    def _on_finished(self, ok, stats, err):
        self._set_syncing(False)
        if ok:
            self._append_log(
                f"\n📊 Kết quả:\n"
                f"  ↑ Đẩy lên Supabase : {stats.get('pushed', 0)} thẻ\n"
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
