"""
_materials.py — Ngữ pháp (grammar_points), Bản dịch (translations) và Chia động từ (conj_*).

Cùng cấu trúc với bảng cùng tên trên Supabase / bản web. Xóa là xóa cứng (trigger đồng bộ ghi tombstone);
mọi sửa đổi đặt updated_at theo giờ máy (trigger dirty đánh dấu để đồng bộ gửi lên).
"""
from ._common import get_connection, _db_op
from infrastructure.id_gen import uuid7

JLPT = ("N5", "N4", "N3", "N2", "N1")
GRAMMAR_FIELDS = ("title", "meaning_vi", "structure", "explanation", "examples", "jlpt_level")
TRANS_FIELDS = ("title", "jp", "vi", "note", "jlpt_level", "glossary")
_NOW = "datetime('now','localtime')"


def _jlpt(v):
    v = (str(v or "")).strip().upper()
    return v if v in JLPT else None


def _txt(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return v or None


def _rows(sql, params=()):
    return [dict(r) for r in get_connection().execute(sql, params).fetchall()]


def _like_all(fields, search):
    toks = (search or "").strip().lower().split()
    conds, params = [], []
    for t in toks:
        conds.append("(" + " OR ".join(f"LOWER(COALESCE({f},'')) LIKE ?" for f in fields) + ")")
        params.extend([f"%{t}%"] * len(fields))
    return conds, params


# ── NGỮ PHÁP ────────────────────────────────────────────────────────────────

@_db_op
def list_grammar(search="", jlpt=""):
    conds, params = _like_all(("title", "meaning_vi", "structure", "explanation", "examples"), search)
    if jlpt:
        conds.append("jlpt_level=?"); params.append(jlpt)
    q = "SELECT * FROM grammar_points" + (" WHERE " + " AND ".join(conds) if conds else "") + " ORDER BY created_at DESC, id DESC"
    return _rows(q, params)


@_db_op
def get_grammar(gid):
    r = get_connection().execute("SELECT * FROM grammar_points WHERE id=?", (gid,)).fetchone()
    return dict(r) if r else None


@_db_op
def add_grammar(data):
    gid = uuid7(); conn = get_connection()
    conn.execute(f"INSERT INTO grammar_points (id,title,meaning_vi,structure,explanation,examples,jlpt_level,created_at,updated_at) "
                 f"VALUES (?,?,?,?,?,?,?,{_NOW},{_NOW})",
                 (gid, (data.get("title") or "").strip(), (data.get("meaning_vi") or "").strip(), _txt(data.get("structure")),
                  _txt(data.get("explanation")), _txt(data.get("examples")), _jlpt(data.get("jlpt_level"))))
    conn.commit()
    return gid


@_db_op
def update_grammar(gid, data):
    conn = get_connection()
    conn.execute(f"UPDATE grammar_points SET title=?, meaning_vi=?, structure=?, explanation=?, examples=?, jlpt_level=?, updated_at={_NOW} WHERE id=?",
                 ((data.get("title") or "").strip(), (data.get("meaning_vi") or "").strip(), _txt(data.get("structure")),
                  _txt(data.get("explanation")), _txt(data.get("examples")), _jlpt(data.get("jlpt_level")), gid))
    conn.commit()


@_db_op
def delete_grammar(gid):
    conn = get_connection(); conn.execute("DELETE FROM grammar_points WHERE id=?", (gid,)); conn.commit()


# ── BẢN DỊCH ────────────────────────────────────────────────────────────────

@_db_op
def list_translations(search="", jlpt=""):
    conds, params = _like_all(("title", "jp", "vi", "note"), search)
    if jlpt:
        conds.append("jlpt_level=?"); params.append(jlpt)
    q = "SELECT * FROM translations" + (" WHERE " + " AND ".join(conds) if conds else "") + " ORDER BY created_at DESC, id DESC"
    return _rows(q, params)


@_db_op
def get_translation(tid):
    r = get_connection().execute("SELECT * FROM translations WHERE id=?", (tid,)).fetchone()
    return dict(r) if r else None


@_db_op
def add_translation(data):
    tid = uuid7(); conn = get_connection()
    conn.execute(f"INSERT INTO translations (id,title,jp,vi,note,jlpt_level,glossary,created_at,updated_at) VALUES (?,?,?,?,?,?,?,{_NOW},{_NOW})",
                 (tid, _txt(data.get("title")), (data.get("jp") or "").strip(), _txt(data.get("vi")), _txt(data.get("note")),
                  _jlpt(data.get("jlpt_level")), _txt(data.get("glossary"))))
    conn.commit()
    return tid


@_db_op
def update_translation(tid, data):
    """Chỉ đổi các trường có trong `data` (vd chỉ glossary khi ghi thêm từ)."""
    sets, params = [], []
    for f in TRANS_FIELDS:
        if f not in data:
            continue
        v = data[f]
        sets.append(f"{f}=?")
        params.append(_jlpt(v) if f == "jlpt_level" else (v or "").strip() if f == "jp" else _txt(v))
    if not sets:
        return
    conn = get_connection()
    conn.execute(f"UPDATE translations SET {', '.join(sets)}, updated_at={_NOW} WHERE id=?", params + [tid])
    conn.commit()


@_db_op
def delete_translation(tid):
    conn = get_connection(); conn.execute("DELETE FROM translations WHERE id=?", (tid,)); conn.commit()


# ── CHIA ĐỘNG TỪ ────────────────────────────────────────────────────────────

def _next_order(table):
    return get_connection().execute(f"SELECT COALESCE(MAX(sort_order), -1) + 1 FROM {table}").fetchone()[0]


@_db_op
def list_conj_forms(include_hidden=True):
    q = "SELECT * FROM conj_forms" + ("" if include_hidden else " WHERE hidden=0") + " ORDER BY sort_order, created_at, id"
    return _rows(q)


@_db_op
def add_conj_form(name, kind=None, hidden=False):
    fid = uuid7(); conn = get_connection()
    conn.execute(f"INSERT INTO conj_forms (id,name,kind,hidden,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,{_NOW},{_NOW})",
                 (fid, name.strip(), kind or None, 1 if hidden else 0, _next_order("conj_forms")))
    conn.commit()
    return fid


@_db_op
def update_conj_form(fid, **patch):
    allowed = {"name": lambda v: v.strip(), "kind": lambda v: v or None, "hidden": lambda v: 1 if v else 0, "sort_order": int}
    sets = [f"{k}=?" for k in patch if k in allowed]
    if not sets:
        return
    conn = get_connection()
    conn.execute(f"UPDATE conj_forms SET {', '.join(sets)}, updated_at={_NOW} WHERE id=?",
                 [allowed[k](v) for k, v in patch.items() if k in allowed] + [fid])
    conn.commit()


@_db_op
def delete_conj_form(fid):
    conn = get_connection(); conn.execute("DELETE FROM conj_forms WHERE id=?", (fid,)); conn.commit()


@_db_op
def move_conj_form(fid, direction):
    """Đổi chỗ với cột kề (tính cả cột đang ẩn)."""
    forms = list_conj_forms(True)
    i = next((n for n, f in enumerate(forms) if f["id"] == fid), -1); j = i + direction
    if i < 0 or j < 0 or j >= len(forms):
        return
    forms[i], forms[j] = forms[j], forms[i]
    for n, f in enumerate(forms):
        if f["sort_order"] != n:
            update_conj_form(f["id"], sort_order=n)


@_db_op
def list_conj_verbs():
    return _rows("SELECT * FROM conj_verbs ORDER BY sort_order, created_at, id")


@_db_op
def add_conj_verbs(items):
    """items: [{'masu','meaning_vi','grp'}] → các id mới theo thứ tự."""
    conn = get_connection(); o = _next_order("conj_verbs"); ids = []
    for v in items:
        vid = uuid7(); ids.append(vid)
        conn.execute(f"INSERT INTO conj_verbs (id,masu,meaning_vi,grp,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,{_NOW},{_NOW})",
                     (vid, v["masu"].strip(), _txt(v.get("meaning_vi")), v.get("grp") or None, o))
        o += 1
    conn.commit()
    return ids


@_db_op
def update_conj_verb(vid, masu, meaning_vi, grp):
    conn = get_connection()
    conn.execute(f"UPDATE conj_verbs SET masu=?, meaning_vi=?, grp=?, updated_at={_NOW} WHERE id=?",
                 (masu.strip(), _txt(meaning_vi), grp or None, vid))
    conn.commit()


@_db_op
def delete_conj_verb(vid):
    conn = get_connection(); conn.execute("DELETE FROM conj_verbs WHERE id=?", (vid,)); conn.commit()


@_db_op
def get_conj_cells():
    """{(verb_id, form_id): value}"""
    return {(r["verb_id"], r["form_id"]): r["value"] for r in get_connection().execute("SELECT verb_id, form_id, value FROM conj_cells")}


@_db_op
def set_conj_cell(verb_id, form_id, value):
    """Rỗng → xóa ô; có chữ → thêm / sửa. Trả True nếu có thay đổi."""
    value = (value or "").strip()[:200]
    conn = get_connection()
    cur = conn.execute("SELECT value FROM conj_cells WHERE verb_id=? AND form_id=?", (verb_id, form_id)).fetchone()
    if (cur[0] if cur else "") == value:
        return False
    if not value:
        conn.execute("DELETE FROM conj_cells WHERE verb_id=? AND form_id=?", (verb_id, form_id))
    elif cur:
        conn.execute(f"UPDATE conj_cells SET value=?, updated_at={_NOW} WHERE verb_id=? AND form_id=?", (value, verb_id, form_id))
    else:
        conn.execute(f"INSERT INTO conj_cells (verb_id,form_id,value,updated_at) VALUES (?,?,?,{_NOW})", (verb_id, form_id, value))
    conn.commit()
    return True


@_db_op
def upsert_conj_cells(rows):
    """rows: [(verb_id, form_id, value)] — ghi hàng loạt (tự điền)."""
    conn = get_connection()
    for v, f, val in rows:
        cur = conn.execute("SELECT value FROM conj_cells WHERE verb_id=? AND form_id=?", (v, f)).fetchone()
        if cur is None:
            conn.execute(f"INSERT INTO conj_cells (verb_id,form_id,value,updated_at) VALUES (?,?,?,{_NOW})", (v, f, val))
        elif cur[0] != val:
            conn.execute(f"UPDATE conj_cells SET value=?, updated_at={_NOW} WHERE verb_id=? AND form_id=?", (val, v, f))
    conn.commit()
    return len(rows)
