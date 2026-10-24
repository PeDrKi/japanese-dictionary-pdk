"""
domain/conjugation.py — quy tắc chia động từ tiếng Nhật (thuần logic, không I/O). Giống hệt bản web (js/core.js).

Đầu vào là thể ます + nhóm (1 = 五段, 2 = 一段, 3 = します / きます); đầu ra là các thể khác.
Mọi hàm trả '' / None khi không suy ra được (cột tự đặt, thiếu nhóm, dạng lạ).
"""

# (mã thể, tên cột mặc định, mô tả tiếng Việt)
CONJ_KINDS = [
    ("dict", "辞書形", "Thể từ điển"), ("nai", "ない形", "Phủ định (ない)"), ("te", "て形", "Thể て"),
    ("ta", "た形", "Quá khứ (た)"), ("potential", "可能形", "Khả năng"), ("volitional", "意向形", "Ý chí (〜よう)"),
    ("imperative", "命令形", "Mệnh lệnh"), ("passive", "受身形", "Bị động"), ("causative", "使役形", "Sai khiến"),
    ("ba", "ば形", "Điều kiện (〜ば)"), ("prohibitive", "禁止形", "Cấm (〜な)"),
    ("masu_neg", "ません形", "ます phủ định"), ("masu_ta", "ました形", "ます quá khứ"), ("nakatta", "なかった形", "Phủ định quá khứ"),
]
CONJ_DEFAULT_KINDS = [k[0] for k in CONJ_KINDS[:11]]
KIND_INFO = {k[0]: k for k in CONJ_KINDS}
GRP_LABEL = {1: "Nhóm 1", 2: "Nhóm 2", 3: "Nhóm 3"}
GRP_HINT = {1: "五段 · のみます, かきます", 2: "一段 · たべます, みます", 3: "します · きます"}

_ROW = {"う": "わいうえお", "く": "かきくけこ", "ぐ": "がぎぐげご", "す": "さしすせそ", "つ": "たちつてと",
        "ぬ": "なにぬねの", "ぶ": "ばびぶべぼ", "む": "まみむめも", "る": "らりるれろ"}
_I2U = {"い": "う", "き": "く", "ぎ": "ぐ", "し": "す", "ち": "つ", "に": "ぬ", "び": "ぶ", "み": "む", "り": "る"}
_U2I = {u: i for i, u in _I2U.items()}


def masu_to_dict(masu, grp):
    """Thể ます → thể từ điển; None nếu không suy ra được."""
    masu = (masu or "").strip()
    if not masu.endswith("ます") or len(masu) < 3:
        return None
    stem = masu[:-2]
    last = stem[-1:]
    if grp == 2:
        return stem + "る"
    if grp == 1:
        return stem[:-1] + _I2U[last] if last in _I2U else None
    if grp == 3:
        if last == "し":
            return stem[:-1] + "する"
        if last == "き":
            return stem[:-1] + "くる"
        if last == "来":
            return stem + "る"
    return None


def dict_to_masu(dict_form, grp):
    """Thể từ điển → thể ます (dùng khi lấy động từ từ thẻ trong thư viện)."""
    d = (dict_form or "").strip()
    if len(d) < 2:
        return None
    last, head = d[-1], d[:-1]
    if grp == 2:
        return head + "ます" if last == "る" else None
    if grp == 1:
        return head + _U2I[last] + "ます" if last in _U2I else None
    if grp == 3:
        if d.endswith("する"):
            return head[:-1] + "します"
        if d.endswith("くる"):
            return head[:-1][:-1] + "きます"
        if last == "る" and head[-1:] == "来":
            return head + "ます"
    return None


def conjugate(masu, grp, kind):
    """Chia từ thể ます + nhóm sang thể `kind`; '' nếu không chia được."""
    masu = (masu or "").strip()
    try:
        grp = int(grp)
    except (TypeError, ValueError):
        grp = 0
    if kind in ("masu_neg", "masu_ta"):
        return masu[:-2] + ("ません" if kind == "masu_neg" else "ました") if masu.endswith("ます") else ""
    d = masu_to_dict(masu, grp)
    if not d:
        return ""
    if kind == "dict":
        return d
    if kind == "prohibitive":
        return d + "な"
    if kind == "nakatta":
        n = conjugate(masu, grp, "nai")
        return n[:-1] + "かった" if n else ""
    if grp == 2:
        st = d[:-1]
        return {"nai": st + "ない", "te": st + "て", "ta": st + "た", "potential": st + "られる", "volitional": st + "よう",
                "imperative": st + "ろ", "passive": st + "られる", "causative": st + "させる", "ba": st + "れば"}.get(kind, "")
    if grp == 1:
        b, u = d[:-1], d[-1]
        r = _ROW.get(u)
        if not r:
            return ""
        if kind == "nai":
            return "ない" if d == "ある" else b + r[0] + "ない"
        if kind in ("te", "ta"):
            t = kind == "te"
            if u == "く" and (d.endswith("行く") or d == "いく" or d.endswith("逝く")):
                return b + ("って" if t else "った")
            m = {"う": "っ", "つ": "っ", "る": "っ", "ぶ": "ん", "む": "ん", "ぬ": "ん", "く": "い", "ぐ": "い", "す": "し"}[u]
            dv = u in "ぶむぬぐ"
            return b + m + (("で" if dv else "て") if t else ("だ" if dv else "た"))
        if d == "ある" and kind in ("potential", "volitional", "imperative", "passive", "causative"):
            return ""
        return {"potential": b + r[3] + "る", "volitional": b + r[4] + "う", "imperative": b + r[3], "passive": b + r[0] + "れる",
                "causative": b + r[0] + "せる", "ba": b + r[3] + "ば"}.get(kind, "")
    if grp == 3:
        if d.endswith("する"):
            p = d[:-2]
            return {"nai": p + "しない", "te": p + "して", "ta": p + "した", "potential": p + "できる", "volitional": p + "しよう",
                    "imperative": p + "しろ", "passive": p + "される", "causative": p + "させる", "ba": p + "すれば"}.get(kind, "")
        pre = d[:-2]
        kanji = d.endswith("来る")

        def k(kana):
            return pre + ("来" if kanji else kana)
        return {"nai": k("こ") + "ない", "te": k("き") + "て", "ta": k("き") + "た", "potential": k("こ") + "られる",
                "volitional": k("こ") + "よう", "imperative": k("こ") + "い", "passive": k("こ") + "られる",
                "causative": k("こ") + "させる", "ba": k("く") + "れば"}.get(kind, "")
    return ""


def guess_group(masu):
    """Gợi ý nhóm 3 (する / くる) từ thể ます; 0 nếu không đoán được."""
    import re
    m = (masu or "").strip()
    return 3 if re.search(r"^(します|きます|来ます)$|[一-鿿]します$", m) else 0
