"""Đối chiếu logic chia động từ / từ vựng với bản web (fixture sinh từ js/core.js) + test riêng của notes."""
import json
import os

from domain.conjugation import conjugate, masu_to_dict, dict_to_masu, guess_group
from domain.notes import (parse_glossary, fmt_glossary, find_spans, split_paras, sentence_of,
                          add_example, example_line, parse_examples)

FX = json.load(open(os.path.join(os.path.dirname(__file__), "..", "fixtures", "web_parity.json"), encoding="utf-8"))


def test_conjugate_matches_web():
    for c in FX["conj"]:
        assert conjugate(c["masu"], c["grp"], c["kind"]) == c["out"], c


def test_masu_to_dict_matches_web():
    for c in FX["m2d"]:
        assert masu_to_dict(c["masu"], c["grp"]) == c["out"], c


def test_dict_to_masu_matches_web():
    for c in FX["d2m"]:
        assert dict_to_masu(c["dict"], c["grp"]) == c["out"], c


def test_parse_glossary_matches_web():
    for c in FX["gl"]:
        got = parse_glossary(c["text"])
        assert [{"term": g["term"], "meaning": g["meaning"]} for g in got] == c["out"], c


def test_known_conjugations():
    assert conjugate("たべます", 2, "te") == "たべて"
    assert conjugate("いきます", 1, "te") == "いって"
    assert conjugate("のみます", 1, "ta") == "のんだ"
    assert conjugate("べんきょうします", 3, "nai") == "べんきょうしない"
    assert conjugate("来ます", 3, "te") == "来て"
    assert conjugate("のみます", 1, "nakatta") == "のまなかった"
    assert guess_group("勉強します") == 3 and guess_group("たべます") == 0


def test_glossary_roundtrip_and_spans():
    items = parse_glossary("丈夫 = chắc\n楽しい")
    assert fmt_glossary(items) == "丈夫 = chắc\n楽しい"
    assert find_spans("丈夫で、丈夫", ["丈夫", "丈"]) == [(0, 2), (4, 6)]
    assert find_spans("abc", []) == []


def test_split_and_sentence():
    assert split_paras("a\n\n b \r\nc") == ["a", "b", "c"]
    p = "今日は友達と映画を見に行きました。とても楽しかったです。"
    assert sentence_of(p, "映画") == "今日は友達と映画を見に行きました。"
    assert sentence_of(p, "楽しい") == p                      # không thấy → cả đoạn


def test_add_example_dedupes_and_limits():
    ex, st = add_example("", example_line("A。", "a"))
    assert (ex, st) == ("A。 | a", "ok")
    ex2, st2 = add_example(ex, "A。 | khác")
    assert st2 == "dup" and ex2 == ex
    ex3, st3 = add_example(ex, "B。")
    assert st3 == "ok" and ex3 == "A。 | a\nB。"
    assert add_example("x" * 7899, "yy")[1] == "toolong"
    assert parse_examples("A | a\nB") == [("A", "a"), ("B", "")]
