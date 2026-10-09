import pytest

from app.core.discussions.body.errors import InvalidBodyError
from app.core.discussions.body.nodes import parse_body
from app.core.discussions.body.walker import (
    MAX_DISTINCT_MENTIONS,
    MAX_NODE_DEPTH,
    MAX_NODES,
    MAX_TEXT_CHARS,
    analyze,
    enforce_limits,
    reject_empty,
    walk,
)
from tests.core.discussions.conftest import (
    bullets,
    doc,
    item,
    mention,
    ordered,
    para,
    text,
)

HARD_BREAK = {"type": "hardBreak"}


def nested_list(depth):
    node = bullets(item(para(text("leaf"))))
    for _ in range(depth - 1):
        node = bullets(item(para(text("x")), node))
    return node


# ── Pre-parse limits ─────────────────────────────────────────────────────────


def test_valid_body_within_limits():
    enforce_limits(
        doc(
            para(text("hello"), mention(42), mention(7)),
            ordered(item(para(text("abc")))),
        )
    )


def test_text_limit():
    enforce_limits(doc(para(text("a" * MAX_TEXT_CHARS))))
    with pytest.raises(InvalidBodyError, match="characters"):
        enforce_limits(doc(para(text("a" * MAX_TEXT_CHARS), text("b"))))


def test_node_limit():
    # doc + paragraph + n inline nodes
    enforce_limits(doc(para(*[HARD_BREAK] * (MAX_NODES - 2))))
    with pytest.raises(InvalidBodyError, match="nodes"):
        enforce_limits(doc(para(*[HARD_BREAK] * (MAX_NODES - 1))))


def test_mention_limit_counts_distinct_ids():
    enforce_limits(doc(para(*[mention(1)] * 50)))
    # 42 and "42" are the same user
    same = [mention(i) for i in range(1, MAX_DISTINCT_MENTIONS)] + [
        mention(42),
        mention("42"),
    ]
    enforce_limits(doc(para(*same)))
    too_many = [mention(i) for i in range(1, MAX_DISTINCT_MENTIONS + 2)]
    with pytest.raises(InvalidBodyError, match="mentions"):
        enforce_limits(doc(para(*too_many)))


def test_list_depth_limit():
    enforce_limits(doc(nested_list(3)))
    with pytest.raises(InvalidBodyError, match="lists nest"):
        enforce_limits(doc(nested_list(4)))


def test_node_depth_limit_without_lists():
    # Invalid shape, but must be stopped by the scan, not by parser recursion.
    node = text("x")
    for _ in range(50_000):
        node = {"type": "paragraph", "content": [node]}
    with pytest.raises(InvalidBodyError, match="deeper than"):
        enforce_limits(doc(node))


def test_deepest_valid_body_within_node_depth():
    raw = doc(nested_list(3))
    enforce_limits(raw)
    parse_body(1, raw)
    assert MAX_NODE_DEPTH == 8


def test_limits_apply_to_unknown_nodes():
    # The scan counts anything under ``content``; it does not validate types.
    with pytest.raises(InvalidBodyError, match="nodes"):
        enforce_limits(doc(*[{"type": "heading"}] * MAX_NODES))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "hello",
        [],
        {"type": "doc", "content": "nope"},
        {"type": "doc", "content": [1, None, "x", []]},
        doc(para({"type": "text", "text": 5})),
        doc(para({"type": "mention", "attrs": "bad"})),
        doc(para({"type": "mention", "attrs": {"id": {"a": 1}}})),
    ],
)
def test_malformed_shapes_are_left_to_the_parser(raw):
    enforce_limits(raw)


# ── Post-parse facts ─────────────────────────────────────────────────────────


def test_walk_is_document_order():
    parsed = parse_body(
        1, doc(para(text("a"), mention(7)), bullets(item(para(text("b")))))
    )
    assert [n.type for n in walk(parsed)] == [
        "doc",
        "paragraph",
        "text",
        "mention",
        "bulletList",
        "listItem",
        "paragraph",
        "text",
    ]


def test_analyze_mention_ids_distinct_in_order():
    facts = analyze(
        parse_body(1, doc(para(mention(42), text(" "), mention(7), mention("42"))))
    )
    assert facts.mention_ids == (42, 7)
    assert facts.has_content


@pytest.mark.parametrize(
    "raw",
    [
        doc(para()),  # Tiptap's empty editor
        doc(para(text("   \n\t "))),
        doc(para(), para(HARD_BREAK)),
        doc(bullets(item(para(text(" "))))),
    ],
)
def test_empty_bodies_rejected(raw):
    facts = analyze(parse_body(1, raw))
    assert not facts.has_content
    with pytest.raises(InvalidBodyError, match="empty"):
        reject_empty(facts)


def test_mention_only_is_not_empty():
    reject_empty(analyze(parse_body(1, doc(para(mention(42))))))
