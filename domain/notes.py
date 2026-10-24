"""
domain/notes.py — logic thuần cho Bản dịch & Ngữ pháp (giống bản web): cột từ vựng "từ = nghĩa",
tách đoạn / câu, tìm vị trí từ trong bài để gạch chân, thêm ví dụ vào mẫu ngữ pháp.
"""
import re

GLOSSARY_MAX = 20000


def split_paras(text):
    """Chia thành các đoạn (mỗi dòng không rỗng là một đoạn)."""
    return [x.strip() for x in re.split(r"\r?\n+", str(text or "")) if x.strip()]


def parse_glossary(text):
    """Mỗi dòng 'từ = nghĩa' (dấu = hoặc ＝) → [{'term', 'meaning'}]. Dòng không có dấu = là từ chưa có nghĩa."""
    out = []
    for line in re.split(r"\r?\n", str(text or "")):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)\s*[=＝]\s*(.*)$", line)
        g = {"term": m.group(1).strip(), "meaning": m.group(2).strip()} if m else {"term": line, "meaning": ""}
        if g["term"]:
            out.append(g)
    return out


def fmt_glossary(items):
    return "\n".join(f"{g['term']} = {g['meaning']}" if g.get("meaning") else g["term"] for g in items)


def find_spans(text, terms):
    """Vị trí (bắt đầu, kết thúc) các từ trong `text` cần gạch chân; từ dài được ưu tiên trước, không chồng nhau."""
    ts = sorted({t for t in (terms or []) if t}, key=lambda t: -len(t))
    if not ts:
        return []
    rx = re.compile("|".join(re.escape(t) for t in ts))
    return [(m.start(), m.end()) for m in rx.finditer(text or "")]


_SENT = re.compile(r"[^。！？!?]*[。！？!?]?")


def sentence_of(para, sel):
    """Câu (trong đoạn) chứa đoạn chữ `sel`; không thấy thì trả cả đoạn."""
    parts = [x for x in _SENT.findall(para or "") if x.strip()]
    return next((x for x in parts if sel in x), para).strip()


def example_line(jp, vi=""):
    """Một dòng ví dụ ngữ pháp: 'câu tiếng Nhật | nghĩa tiếng Việt'."""
    jp = (jp or "").strip()
    return f"{jp} | {vi.strip()}" if vi and vi.strip() else jp


def add_example(examples, line, limit=7900):
    """Nối `line` vào cuối trường examples. Trả (examples mới, trạng thái): 'ok' | 'dup' | 'toolong'."""
    jp = line.split("|")[0].strip()
    cur = examples or ""
    if any(l.split("|")[0].strip() == jp for l in cur.split("\n")):
        return cur, "dup"
    nxt = (cur.rstrip() + "\n" if cur else "") + line
    if len(nxt) > limit:
        return cur, "toolong"
    return nxt, "ok"


def parse_examples(text):
    """Trường examples → [(jp, vi)]."""
    out = []
    for line in str(text or "").split("\n"):
        if not line.strip():
            continue
        a, _, b = line.partition("|")
        out.append((a.strip(), b.strip()))
    return out


_HIRA = set("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽゃゅょっー")
_KATA = set("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポャュョッー")


def guess_card_type(word):
    """Đoán loại thẻ từ chữ: hiragana / katakana / kanji (1 chữ Hán) / vocab."""
    w = (word or "").strip()
    if w and all(c in _HIRA for c in w):
        return "hiragana"
    if w and all(c in _KATA for c in w):
        return "katakana"
    if len(w) == 1 and "一" <= w <= "鿿":
        return "kanji"
    return "vocab"
