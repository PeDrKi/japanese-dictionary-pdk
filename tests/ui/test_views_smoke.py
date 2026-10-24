"""Smoke test giao diện: dựng App thật và mở từng màn hình mới. Tự bỏ qua nếu máy không có tkinter / màn hình (vd CI không GUI).
Chạy có GUI ảo:  xvfb-run -a python -m pytest tests/ui -q"""
import pytest

tk = pytest.importorskip("tkinter")
ctk = pytest.importorskip("customtkinter")


@pytest.fixture
def app(fresh_db):
    try:
        from ui.app import App
        a = App()
    except tk.TclError:
        pytest.skip("không có màn hình (DISPLAY)")
    a.update()
    yield a
    a.destroy()


def test_new_tabs_open_and_basic_flow(app):
    ms = app.material_service
    gid, _ = ms.save_grammar(None, {"title": "〜てから", "meaning_vi": "sau khi", "examples": "A。 | a"})
    ms.add_default_forms(); ms.save_verb(None, "たべます", "ăn", 2)
    tid, _ = ms.save_translation(None, {"jp": "今日は友達と映画を見ました。", "vi": "Hôm nay xem phim với bạn.", "glossary": "映画 = phim"})
    for tab in ("grammar", "conj", "trans", "radicals", "stats", "table"):
        app._switch_tab(tab); app.update()
    app._switch_tab("trans"); app.trans.open_item(tid); app.update()
    for mode in ("pair", "hide", "jp", "two"):
        app.trans._mode = mode; app.trans._show_reader(); app.update()
    txt = app.trans._txt
    i = txt.search("友達", "1.0"); txt.tag_add("sel", i, f"{i}+2c"); app.trans._update_sel()
    assert app.trans._sel["text"] == "友達" and app.trans._sel["sentence"].startswith("今日は")
    app._switch_tab("conj")
    key = next(iter(app.conj._entries)); e = app.conj._entries[key]; e.delete(0, "end"); e.insert(0, "テスト"); app.conj._commit(key)
    assert ms.cells()[key] == "テスト"
    app._switch_tab("grammar"); assert app.grammar._sel == gid
