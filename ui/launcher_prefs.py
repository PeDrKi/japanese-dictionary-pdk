"""ui/launcher_prefs.py — nhớ lựa chọn lần ôn trước của các hộp thoại 'Bắt đầu ôn'."""
from infrastructure import settings

_KEY = "launcher_prefs"


def restore(name: str, variables: dict, allowed: dict = None, skip=()):
    """Gán lại giá trị đã lưu cho các tk Variable. `allowed[k]` = danh sách giá trị hợp lệ
    (giá trị không còn hợp lệ, vd. deck đã xóa, bị bỏ qua)."""
    saved = (settings.get(_KEY, {}) or {}).get(name, {})
    if not isinstance(saved, dict):
        return
    for k, var in variables.items():
        if k in skip or k not in saved:
            continue
        v = saved[k]
        if allowed and k in allowed and v not in allowed[k]:
            continue
        try:
            var.set(v)
        except Exception:
            pass


def save(name: str, variables: dict):
    try:
        all_prefs = dict(settings.get(_KEY, {}) or {})
        all_prefs[name] = {k: v.get() for k, v in variables.items()}
        settings.set(_KEY, all_prefs)
    except Exception:
        pass
