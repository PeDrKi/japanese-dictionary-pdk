"""
infrastructure/cloud_config.py — cấu hình đồng bộ đám mây (không phụ thuộc giao diện, test được).

Lưu trong settings.json: URL dự án, khoá anon/publishable (công khai, an toàn nhờ RLS), email,
và refresh token (thu hồi được; KHÔNG lưu mật khẩu). KHÔNG dùng khoá service_role/secret ở đây.
"""
from infrastructure import settings
from infrastructure.cloud_sync import CloudSync, PasswordAuth

K_URL, K_KEY, K_EMAIL, K_TOKEN = "cloud_url", "cloud_key", "cloud_email", "cloud_refresh_token"
CLOUD_SECRET_KEYS = (K_KEY, K_EMAIL, K_TOKEN, K_URL)


def get_saved_config() -> dict | None:
    """None nếu chưa thiết lập (chưa có URL/khoá/phiên) → app không tự đồng bộ."""
    url = (settings.get(K_URL, "") or "").strip()
    key = (settings.get(K_KEY, "") or "").strip()
    token = (settings.get(K_TOKEN, "") or "").strip()
    if not url or not key or not token:
        return None
    return {"url": url, "key": key, "email": (settings.get(K_EMAIL, "") or "").strip(), "refresh_token": token}


def looks_like_service_role(key: str) -> bool:
    """Cảnh báo nếu người dùng dán nhầm khoá quyền admin (JWT có role=service_role / khoá sb_secret_)."""
    import base64
    import json
    if key.startswith("sb_secret_"):
        return True
    try:
        payload = key.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("role") == "service_role"
    except Exception:
        return False


def save_config(url, key, email, refresh_token=None):
    settings.update({K_URL: url.strip().rstrip("/"), K_KEY: key.strip(), K_EMAIL: email.strip()})
    if refresh_token is not None:
        settings.set(K_TOKEN, refresh_token)


def forget_session():
    settings.set(K_TOKEN, "")


def make_auth(cfg: dict, password: str | None = None) -> PasswordAuth:
    return PasswordAuth(cfg["url"], cfg["key"], email=cfg.get("email") or None, password=password or None,
                        refresh_token=cfg.get("refresh_token") or None,
                        on_refresh_token=lambda t: settings.set(K_TOKEN, t))


def make_syncer(cfg: dict, password: str | None = None, progress_cb=None, timeout: float = 30.0,
                deadline_s: float | None = None, wait_lock_s: float = 0.0) -> CloudSync:
    return CloudSync(supabase_url=cfg["url"], anon_key=cfg["key"], auth=make_auth(cfg, password),
                     progress_cb=progress_cb, timeout=timeout, deadline_s=deadline_s, wait_lock_s=wait_lock_s)
