"""
application/material_service.py — use case cho Ngữ pháp, Bản dịch (kèm cột từ vựng) và Chia động từ.

Giống bản web: ghi từ mới khi đang đọc → cột từ vựng của bài / thẻ từ vựng / ví dụ ngữ pháp; bảng chia động từ tự điền
theo quy tắc nhưng sửa tay từng ô, thêm / xóa / ẩn / đổi thứ tự cột.
"""
from domain.conjugation import CONJ_KINDS, CONJ_DEFAULT_KINDS, KIND_INFO, conjugate, dict_to_masu
from domain.notes import (add_example, example_line, fmt_glossary, guess_card_type, parse_glossary,
                          sentence_of, split_paras, GLOSSARY_MAX)
from domain.repositories import MaterialRepository
from domain.validators import build_card_data


class MaterialService:
    def __init__(self, repo: MaterialRepository, card_service=None, deck_service=None):
        self._r = repo
        self._cards = card_service
        self._decks = deck_service

    # ── Ngữ pháp ────────────────────────────────────────────────────────────
    def list_grammar(self, search="", jlpt=""):
        return self._r.list_grammar(search, jlpt)

    def get_grammar(self, gid):
        return self._r.get_grammar(gid)

    def save_grammar(self, gid, data):
        """Trả (id, lỗi). Lỗi là chuỗi tiếng Việt hoặc None."""
        if not (data.get("title") or "").strip():
            return None, "Cần nhập mẫu câu"
        if len(data.get("examples") or "") > 8000:
            return None, "Phần ví dụ quá dài (tối đa 8000 ký tự)"
        if gid:
            self._r.update_grammar(gid, data)
            return gid, None
        return self._r.add_grammar(data), None

    def delete_grammar(self, gid):
        self._r.delete_grammar(gid)

    def add_example(self, gid, line):
        """Nối 1 ví dụ vào mẫu ngữ pháp. Trả 'ok' | 'dup' | 'toolong' | 'missing'."""
        g = self._r.get_grammar(gid)
        if not g:
            return "missing"
        nxt, st = add_example(g.get("examples"), line)
        if st == "ok":
            self._r.update_grammar(gid, {**g, "examples": nxt})
        return st

    # ── Bản dịch ────────────────────────────────────────────────────────────
    def list_translations(self, search="", jlpt=""):
        return self._r.list_translations(search, jlpt)

    def get_translation(self, tid):
        return self._r.get_translation(tid)

    def save_translation(self, tid, data):
        if not (data.get("jp") or "").strip():
            return None, "Cần nhập đoạn tiếng Nhật"
        if len(data["jp"]) > 30000:
            return None, "Phần tiếng Nhật quá dài (tối đa 30000 ký tự)"
        if len(data.get("vi") or "") > 40000:
            return None, "Phần tiếng Việt quá dài (tối đa 40000 ký tự)"
        if len(data.get("glossary") or "") > GLOSSARY_MAX:
            return None, "Cột từ vựng quá dài"
        if tid:
            self._r.update_translation(tid, data)
            return tid, None
        return self._r.add_translation(data), None

    def delete_translation(self, tid):
        self._r.delete_translation(tid)

    def glossary(self, tid):
        t = self._r.get_translation(tid)
        return parse_glossary(t.get("glossary") if t else "")

    def save_glossary(self, tid, items):
        self._r.update_translation(tid, {"glossary": fmt_glossary(items)})

    def set_glossary_term(self, tid, index, term, meaning):
        """index None → thêm mới (nếu trùng từ thì cập nhật nghĩa). Trả danh sách mới."""
        items = self.glossary(tid)
        term, meaning = term.strip(), (meaning or "").strip()
        if not term:
            return items
        if index is None:
            same = next((g for g in items if g["term"] == term), None)
            if same:
                same["meaning"] = meaning or same["meaning"]
            else:
                items.append({"term": term, "meaning": meaning})
        elif 0 <= index < len(items):
            items[index] = {"term": term, "meaning": meaning}
        self.save_glossary(tid, items)
        return items

    def delete_glossary_term(self, tid, index):
        items = self.glossary(tid)
        if 0 <= index < len(items):
            del items[index]
            self.save_glossary(tid, items)
        return items

    # ── Từ mới → thẻ từ vựng ────────────────────────────────────────────────
    def card_preset(self, t, term, meaning=""):
        """Dữ liệu điền sẵn cho thẻ từ bài đọc `t`: câu chứa từ làm ví dụ, bản dịch (khi ghép cặp đoạn), nguồn = tên bài."""
        jp, vis = split_paras(t["jp"]), split_paras(t.get("vi"))
        para = next((x for x in jp if term in x), "")
        sen = sentence_of(para, term) if para else ""
        i = jp.index(para) if para else -1
        return {
            "type": guess_card_type(term), "character": term, "meaning_vi": meaning,
            "example_jp": "" if sen == term else sen,
            "example_vi": vis[i] if (para and len(vis) == len(jp) and sen == para) else "",
            "source": (t.get("title") or t["jp"][:20]).strip(),
        }

    def card_exists(self, character):
        if not self._cards:
            return False
        return any(c["character"] == character for c in self._cards.list_cards(search=character) if c["character"] == character)

    def cards_from_glossary(self, tid, picks, deck_ids=()):
        """Tạo thẻ cho các từ trong cột từ vựng (`picks` = chỉ số). Bỏ qua từ đã có thẻ hoặc chưa có nghĩa.
        Trả (số thẻ đã tạo, số bỏ qua)."""
        t = self._r.get_translation(tid)
        items = parse_glossary(t.get("glossary")) if t else []
        made, skipped = 0, 0
        for i in picks:
            if not (0 <= i < len(items)):
                continue
            g = items[i]
            if not g["meaning"] or self.card_exists(g["term"]):
                skipped += 1
                continue
            p = self.card_preset(t, g["term"], g["meaning"])
            cid = self._cards.add(build_card_data(
                card_type=p["type"], character=p["character"], meaning_vi=p["meaning_vi"],
                example_jp=p["example_jp"], example_vi=p["example_vi"], source=p["source"]))
            for d in deck_ids:
                self._decks.add_card(d, cid)
            made += 1
        return made, skipped

    # ── Chia động từ ────────────────────────────────────────────────────────
    def forms(self, include_hidden=True):
        return self._r.list_conj_forms(include_hidden)

    def verbs(self):
        return self._r.list_conj_verbs()

    def cells(self):
        return self._r.get_conj_cells()

    def add_default_forms(self):
        """Thêm các thể thông dụng còn thiếu. Trả id các cột vừa thêm."""
        have = {f["kind"] for f in self._r.list_conj_forms(True)}
        return [self._r.add_conj_form(k[1], k[0]) for k in CONJ_KINDS if k[0] in CONJ_DEFAULT_KINDS and k[0] not in have]

    def save_form(self, fid, name, kind, hidden):
        name = (name or "").strip()
        if not name:
            return None
        if fid:
            self._r.update_conj_form(fid, name=name, kind=kind or None, hidden=hidden)
            return fid
        return self._r.add_conj_form(name, kind or None, hidden)

    def delete_form(self, fid):
        self._r.delete_conj_form(fid)

    def toggle_form(self, fid, hidden):
        self._r.update_conj_form(fid, hidden=hidden)

    def move_form(self, fid, direction):
        self._r.move_conj_form(fid, direction)

    def save_verb(self, vid, masu, meaning_vi, grp, fill=True):
        """Thêm / sửa động từ; fill → điền các ô trống theo quy tắc. Trả (id, số ô điền)."""
        masu = (masu or "").strip()
        if not masu or grp not in (1, 2, 3):
            return None, 0
        if vid:
            self._r.update_conj_verb(vid, masu, meaning_vi, grp)
        else:
            vid = self._r.add_conj_verbs([{"masu": masu, "meaning_vi": meaning_vi, "grp": grp}])[0]
        return vid, (self.fill(verb_ids=[vid]) if fill else 0)

    def has_masu(self, masu, exclude_id=None):
        return any(v["masu"] == masu and v["id"] != exclude_id for v in self._r.list_conj_verbs())

    def delete_verb(self, vid):
        self._r.delete_conj_verb(vid)

    def set_cell(self, verb_id, form_id, value):
        return self._r.set_conj_cell(verb_id, form_id, value)

    def fill(self, verb_ids=None, form_ids=None, overwrite=False):
        """Tự điền ô theo quy tắc chia (chỉ cột có kind). overwrite=False giữ ô đã có chữ. Trả số ô đã ghi."""
        cells = self._r.get_conj_cells()
        forms = [f for f in self._r.list_conj_forms(True) if f["kind"] and (not form_ids or f["id"] in form_ids)]
        rows = []
        for v in self._r.list_conj_verbs():
            if verb_ids and v["id"] not in verb_ids:
                continue
            for f in forms:
                if not overwrite and cells.get((v["id"], f["id"])):
                    continue
                val = conjugate(v["masu"], v["grp"], f["kind"])
                if val:
                    rows.append((v["id"], f["id"], val))
        return self._r.upsert_conj_cells(rows) if rows else 0

    def candidates(self):
        """Thẻ động từ trong thư viện chưa có trong bảng: [{'card','masu','grp'}]."""
        if not self._cards:
            return []
        have = {v["masu"] for v in self._r.list_conj_verbs()}
        out = []
        for c in self._cards.list_cards(pos_filter=None):
            grp = {"verb1": 1, "verb2": 2, "verb3": 3}.get(c.get("pos"))
            if not grp:
                continue
            masu = dict_to_masu(c["character"], grp) or dict_to_masu(c.get("reading_kana"), grp)
            if not masu or masu in have:
                continue
            have.add(masu)
            out.append({"card": c, "masu": masu, "grp": grp})
        return out

    def import_candidates(self, picks):
        ids = self._r.add_conj_verbs([{"masu": p["masu"], "meaning_vi": p["card"].get("meaning_vi"), "grp": p["grp"]} for p in picks])
        self.fill(verb_ids=ids)
        return len(ids)
