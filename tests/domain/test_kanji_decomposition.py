"""
Tests for domain/kanji_decomposition.py — pure IDS-string parsing, no
data source involved.
"""
import pytest

from domain.kanji_decomposition import parse_ids, IdsParseError


def test_parses_simple_two_operand_ids():
    node = parse_ids("⿰日音")
    assert node.operator == "⿰"
    assert [c.character for c in node.children] == ["日", "音"]
    assert all(c.is_leaf for c in node.children)


def test_leaf_character_alone_has_no_operator():
    node = parse_ids("日")
    assert node.operator is None
    assert node.character == "日"
    assert node.is_leaf


def test_parses_nested_ids_within_one_entry():
    # 亟's IDS: ⿱ combining (⿻ combining 了 and 叹) and 一
    node = parse_ids("⿱⿻了叹一")
    assert node.operator == "⿱"
    assert len(node.children) == 2
    inner, last = node.children
    assert inner.operator == "⿻"
    assert [c.character for c in inner.children] == ["了", "叹"]
    assert last.character == "一"


def test_three_operand_ids_parses_all_three_children():
    node = parse_ids("⿲彳寺亍")
    assert node.operator == "⿲"
    assert [c.character for c in node.children] == ["彳", "寺", "亍"]


def test_empty_string_is_a_parse_error():
    with pytest.raises(IdsParseError):
        parse_ids("")


def test_trailing_extra_characters_is_a_parse_error():
    with pytest.raises(IdsParseError):
        parse_ids("日音")  # two leaves with no combining IDC between them


def test_truncated_ids_is_a_parse_error():
    with pytest.raises(IdsParseError):
        parse_ids("⿰日")  # ⿰ needs two operands, only got one
