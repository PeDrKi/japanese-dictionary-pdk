"""cloud_config: nhận diện khoá nhầm quyền, lưu/đọc cấu hình, quên phiên."""
import base64
import json

from infrastructure import cloud_config as cc
from infrastructure import settings as settings_module


def _jwt(role):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b({'alg': 'HS256'})}.{b({'role': role})}.sig"


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module, "_SETTINGS_PATH", str(tmp_path / "s.json"))
    monkeypatch.setattr(settings_module, "_cache", {})


def test_service_role_detection():
    assert cc.looks_like_service_role(_jwt("service_role"))
    assert cc.looks_like_service_role("sb_secret_abc")
    assert not cc.looks_like_service_role(_jwt("anon"))
    assert not cc.looks_like_service_role("sb_publishable_abc")
    assert not cc.looks_like_service_role("garbage")


def test_roundtrip_and_forget(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    assert cc.get_saved_config() is None
    cc.save_config(" https://x.supabase.co/ ", " key ", " a@b.c ", refresh_token="rt")
    cfg = cc.get_saved_config()
    assert cfg == {"url": "https://x.supabase.co", "key": "key", "email": "a@b.c", "refresh_token": "rt"}
    cc.forget_session()
    assert cc.get_saved_config() is None  # không còn phiên → không tự đồng bộ
    assert settings_module.get(cc.K_URL) == "https://x.supabase.co"


def test_backup_excludes_cloud_keys(tmp_path, monkeypatch):
    _fresh(monkeypatch, tmp_path)
    cc.save_config("https://x.supabase.co", "k", "a@b.c", refresh_token="rt")
    from infrastructure import backup
    monkeypatch.setattr(backup, "_SETTINGS_PATH", str(tmp_path / "s.json"))
    out = json.loads(backup._sanitized_settings_json())
    for k in cc.CLOUD_SECRET_KEYS:
        assert k not in out
