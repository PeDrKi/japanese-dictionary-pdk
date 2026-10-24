"""
sync_dialog.py — Hộp thoại đồng bộ với Supabase (cùng dữ liệu với bản web).
Đăng nhập bằng email + mật khẩu tài khoản Supabase (giống web); dữ liệu của bạn được bảo vệ bằng RLS.
"""
from ui.threadsafe import call_in_ui
import customtkinter as ctk
from tkinter import messagebox
import threading

from infrastructure import settings
from infrastructure.cloud_config import (
    get_saved_config, save_config, forget_session, make_syncer, looks_like_service_role,
    K_URL, K_KEY, K_EMAIL,
)

__all__ = ["SyncDialog", "get_saved_config"]


class SyncDialog(ctk.CTkToplevel):

    def __init__(self, master, on_sync_done=None):
        super().__init__(master)
        self.on_sync_done = on_sync_done
        self.title("☁️  Đồng bộ Supabase")
        self.geometry("560x640")
        self.resizable(False, True)
        self.grab_set()
        self.lift()
        self.focus_force()
        self._syncing = False
        self._build()
        self._load_saved_settings()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _entry(self, parent, row, label, var, placeholder="", show=None):
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=row * 2, column=0, padx=14, pady=(10 if row else 14, 2), sticky="w")
        e = ctk.CTkEntry(parent, textvariable=var, placeholder_text=placeholder, height=32, show=show)
        e.grid(row=row * 2 + 1, column=0, padx=14, pady=(0, 4), sticky="ew")
        return e

    def _build(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self, fg_color=("gray88", "gray18"), corner_radius=0, height=56)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="☁️  Đồng bộ 2 chiều với Supabase (web ↔ desktop)",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(side="left", padx=16, pady=14)

        cfg = ctk.CTkFrame(self, fg_color=("gray90", "gray20"), corner_radius=10)
        cfg.grid(row=1, column=0, sticky="ew", padx=16, pady=(14, 0))
        cfg.grid_columnconfigure(0, weight=1)
        self._url_var, self._key_var = ctk.StringVar(), ctk.StringVar()
        self._email_var, self._pw_var = ctk.StringVar(), ctk.StringVar()
        self._entry(cfg, 0, "🌐  Project URL", self._url_var, "https://xxxxxxxx.supabase.co")
        self._entry(cfg, 1, "🔑  Anon / Publishable key  (KHÔNG dùng service_role)", self._key_var, "eyJhbGciOi… hoặc sb_publishable_…", show="•")
        self._entry(cfg, 2, "📧  Email tài khoản (cùng tài khoản dùng trên web)", self._email_var, "ban@example.com")
        self._pw_entry = self._entry(cfg, 3, "🔒  Mật khẩu  (chỉ cần khi đăng nhập lần đầu)", self._pw_var, "để trống nếu đã đăng nhập", show="•")
        ctk.CTkFrame(cfg, height=8, fg_color="transparent").grid(row=8, column=0)

        info = ctk.CTkFrame(self, fg_color=("gray88", "gray22"), corner_radius=8)
        info.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 0))
        ctk.CTkLabel(
            info,
            text=("ℹ️  Dùng chung dữ liệu với bản web:\n"
                  "  1. Supabase → SQL Editor → chạy file docs/supabase_schema.sql (1 lần)\n"
                  "  2. Settings → API → copy Project URL + anon/publishable key\n"
                  "  3. Đăng nhập bằng email/mật khẩu như trên web (tạo tài khoản ở web nếu chưa có)\n"
                  "  Mật khẩu không được lưu; chỉ lưu phiên (có thể thu hồi). Xung đột: bản mới hơn thắng,\n"
                  "  giá trị bị thay được ghi lại trong log. File âm thanh/ảnh chỉ nằm trên máy này."),
            font=ctk.CTkFont(size=10), text_color=("gray45", "gray60"), justify="left", anchor="w"
        ).pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(self, text="📋  Log", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=("gray50", "gray55"), anchor="w").grid(row=3, column=0, sticky="w", padx=18, pady=(12, 2))
        self._log_box = ctk.CTkTextbox(self, height=140, font=ctk.CTkFont(family="Consolas", size=11),
                                       state="disabled", corner_radius=6)
        self._log_box.grid(row=4, column=0, sticky="nsew", padx=16, pady=(0, 6))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 16))
        ctk.CTkButton(btn_row, text="✕  Đóng", width=90, height=38, fg_color=("gray75", "gray35"),
                      text_color=("gray10", "gray90"), command=self._on_close).pack(side="left")
        ctk.CTkButton(btn_row, text="Đăng xuất", width=90, height=38, fg_color=("gray75", "gray35"),
                      text_color=("gray10", "gray90"), command=self._logout).pack(side="left", padx=(8, 0))
        self._sync_btn = ctk.CTkButton(btn_row, text="☁️  Đồng bộ ngay", height=38, command=self._start_sync)
        self._sync_btn.pack(side="right")

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_saved_settings(self):
        self._url_var.set(settings.get(K_URL, "") or settings.get("supabase_url", ""))   # URL cũ dùng lại được; khoá cũ thì không
        self._key_var.set(settings.get(K_KEY, ""))
        self._email_var.set(settings.get(K_EMAIL, ""))

    def _logout(self):
        forget_session()
        self._append_log("Đã xóa phiên đăng nhập trên máy này. Lần sau cần nhập lại mật khẩu.")

    # ── Sync ──────────────────────────────────────────────────────────────────

    def _start_sync(self):
        if self._syncing:
            return
        url, key = self._url_var.get().strip(), self._key_var.get().strip()
        email, pw = self._email_var.get().strip(), self._pw_var.get()
        saved = get_saved_config()
        if not url or not key or not (email or saved):
            messagebox.showwarning("Thiếu thông tin", "Nhập Project URL, anon key và email.", parent=self)
            return
        if looks_like_service_role(key):
            messagebox.showerror("Sai loại khoá",
                                 "Đây là khoá quyền quản trị (service_role/secret). KHÔNG dùng ở ứng dụng này — "
                                 "hãy dùng khoá anon / publishable.", parent=self)
            return
        if not saved and not pw:
            messagebox.showwarning("Thiếu mật khẩu", "Lần đầu cần nhập mật khẩu tài khoản Supabase.", parent=self)
            return
        # đổi URL/khoá/email → bỏ phiên cũ
        if saved and (saved["url"] != url.rstrip("/") or saved["key"] != key or saved["email"] != email):
            forget_session()
            saved = None
        save_config(url, key, email)
        cfg = {"url": url.rstrip("/"), "key": key, "email": email,
               "refresh_token": (get_saved_config() or {}).get("refresh_token", "")}
        self._clear_log()
        self._set_syncing(True)

        def _run():
            syncer = make_syncer(cfg, password=pw, progress_cb=self._append_log_safe)
            ok, stats, err = syncer.sync()
            call_in_ui(self, lambda: self._on_finished(ok, stats, err))

        threading.Thread(target=_run, daemon=True).start()

    def _on_finished(self, ok, stats, err):
        self._set_syncing(False)
        self._pw_var.set("")
        if ok:
            lines = [f"\n📊 Kết quả:",
                     f"  ↑ Đã gửi lên      : {stats.get('pushed', 0)}",
                     f"  ↓ Đã kéo về       : {stats.get('pulled', 0)}",
                     f"  🔀 Đã gộp         : {stats.get('merged', 0)}",
                     f"  🗑️ Xóa theo nơi khác: {stats.get('deleted_local', 0)}"]
            for c in stats.get("conflicts", []):
                lines.append("  ⚠️ " + c)
            for e in stats.get("errors", []):
                lines.append("  ❌ " + e)
            self._append_log("\n".join(lines))
            if self.on_sync_done:
                self.on_sync_done()
        else:
            self._append_log(f"\n❌ Lỗi:\n{err}")
            if stats.get("account_mismatch"):
                if messagebox.askyesno("Đổi tài khoản đồng bộ", err + "\n\nĐặt lại liên kết đồng bộ ngay?", parent=self):
                    try:
                        from infrastructure.cloud_sync import reset_sync_state
                        reset_sync_state(new_ids=True)
                        self._append_log("✅ Đã đặt lại liên kết. Bấm 'Đồng bộ ngay' để gửi dữ liệu trên máy lên tài khoản này.")
                    except Exception as e:
                        messagebox.showerror("Không đặt lại được", str(e), parent=self)
            else:
                messagebox.showerror("Đồng bộ thất bại", err, parent=self)

    # ── Log ───────────────────────────────────────────────────────────────────

    def _append_log(self, msg):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _append_log_safe(self, msg):
        call_in_ui(self, lambda m=msg: self._append_log(m))

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _set_syncing(self, syncing):
        self._syncing = syncing
        if syncing:
            self._sync_btn.configure(text="⏳  Đang đồng bộ...", state="disabled", fg_color=("gray60", "gray40"))
        else:
            self._sync_btn.configure(text="☁️  Đồng bộ ngay", state="normal", fg_color=("#3B82F6", "#2563EB"))

    def _on_close(self):
        if self._syncing and not messagebox.askyesno("Đang đồng bộ", "Chưa xong. Vẫn muốn đóng?", parent=self):
            return
        self.destroy()
