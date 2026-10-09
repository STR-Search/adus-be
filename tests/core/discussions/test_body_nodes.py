import pytest

from app.core.discussions.body.errors import InvalidBodyError
from app.core.discussions.body.nodes import parse_body
from tests.core.discussions.conftest import (
    bullets,
    doc,
    item,
    mention,
    ordered,
    para,
    text,
)


def dump(raw):
    return parse_body(1, raw).model_dump(exclude_none=True)


def error_types(exc: InvalidBodyError) -> set[str]:
    return {e["type"] for e in exc.errors}


# ── Accepted content ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("mark", ["bold", "italic", "strike", "underline", "code"])
def test_simple_marks_accepted(mark):
    raw = doc(para(text("hi", marks=[{"type": mark}])))
    assert dump(raw) == raw


def test_link_mark_keeps_only_href():
    raw = doc(
        para(
            text(
                "AirDNA",
                marks=[
                    {
                        "type": "link",
                        "attrs": {
                            "href": "https://example.com/x",
                            "target": "_blank",
                            "rel": "noopener",
                            "class": None,
                        },
                    }
                ],
            )
        )
    )
    link = dump(raw)["content"][0]["content"][0]["marks"][0]
    assert link == {"type": "link", "attrs": {"href": "https://example.com/x"}}


def test_full_document_round_trips():
    raw = doc(
        para(text("ADR looks high, "), mention(42), text("."), {"type": "hardBreak"}),
        bullets(item(para(text("one")), ordered(item(para(text("a"))), start=3))),
        ordered(item(para(text("first")))),
    )
    out = dump(raw)
    assert out["content"][0] == raw["content"][0]
    assert out["content"][1] == raw["content"][1]
    # orderedList attrs are normalized to always carry start.
    assert out["content"][2]["attrs"] == {"start": 1}


def test_empty_paragraph_has_no_content_key():
    assert dump(doc(para())) == {"type": "doc", "content": [{"type": "paragraph"}]}


def test_mention_attrs_stripped_and_id_coerced():
    raw = doc(para(mention("42", label="Jane Doe", mentionSuggestionChar="@")))
    assert dump(raw)["content"][0]["content"][0] == {
        "type": "mention",
        "attrs": {"id": 42},
    }


def test_unknown_keys_and_attrs_dropped():
    raw = doc(
        {"type": "paragraph", "attrs": {"textAlign": "left"}, "content": [text("x")]}
    )
    raw["content"][0]["content"][0]["junk"] = 1
    assert dump(raw) == doc(para(text("x")))


def test_ordered_list_type_attr_dropped():
    raw = doc(ordered(item(para(text("x")))))
    raw["content"][0]["attrs"] = {"start": 5, "type": None}
    assert dump(raw)["content"][0]["attrs"] == {"start": 5}


# ── Rejected content ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "block",
    [
        {"type": "heading", "attrs": {"level": 1}, "content": [text("x")]},
        {"type": "blockquote", "content": [para(text("x"))]},
        {"type": "codeBlock", "content": [text("x")]},
        {"type": "horizontalRule"},
    ],
)
def test_rejected_block_nodes(block):
    with pytest.raises(InvalidBodyError) as exc:
        parse_body(1, doc(block))
    assert "union_tag_invalid" in error_types(exc.value)
    assert exc.value.errors[0]["loc"][:3] == ["body", "content", 0]


@pytest.mark.parametrize(
    "node", [{"type": "image", "attrs": {"src": "x"}}, {"type": "emoji"}]
)
def test_rejected_inline_nodes(node):
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc(para(node)))


def test_rejected_mark():
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc(para(text("x", marks=[{"type": "highlight"}]))))


def test_missing_type_rejected():
    with pytest.raises(InvalidBodyError) as exc:
        parse_body(1, doc({"content": [text("x")]}))
    assert "union_tag_not_found" in error_types(exc.value)


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "data:text/html,hi",
        "ftp://example.com",
        "/relative/path",
        "https://",
        "mailto:a@b.com",
    ],
)
def test_link_scheme_rejected(href):
    raw = doc(para(text("x", marks=[{"type": "link", "attrs": {"href": href}}])))
    with pytest.raises(InvalidBodyError):
        parse_body(1, raw)


def test_link_scheme_case_insensitive_and_stripped():
    raw = doc(
        para(text("x", marks=[{"type": "link", "attrs": {"href": " HTTPS://a.com "}}]))
    )
    assert (
        dump(raw)["content"][0]["content"][0]["marks"][0]["attrs"]["href"]
        == "HTTPS://a.com"
    )


@pytest.mark.parametrize("bad_id", [True, False, 0, -1, 4.5, "abc", None])
def test_bad_mention_ids_rejected(bad_id):
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc(para(mention(bad_id))))


def test_doc_must_have_blocks():
    with pytest.raises(InvalidBodyError):
        parse_body(1, {"type": "doc", "content": []})


def test_root_must_be_doc():
    with pytest.raises(InvalidBodyError):
        parse_body(1, para(text("x")))


@pytest.mark.parametrize("raw", [None, "hello", [], 5])
def test_non_object_body_rejected(raw):
    with pytest.raises(InvalidBodyError):
        parse_body(1, raw)


def test_text_node_cannot_be_empty():
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc(para(text(""))))


def test_list_needs_items():
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc(bullets()))


def test_list_item_must_start_with_paragraph():
    with pytest.raises(InvalidBodyError):
        parse_body(
            1,
            doc(
                bullets(
                    {"type": "listItem", "content": [bullets(item(para(text("x"))))]}
                )
            ),
        )


def test_list_item_rejects_second_paragraph():
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc(bullets(item(para(text("a")), para(text("b"))))))


def test_list_item_child_must_be_list_item():
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc({"type": "bulletList", "content": [para(text("x"))]}))


def test_inline_not_allowed_at_block_level():
    with pytest.raises(InvalidBodyError):
        parse_body(1, doc(text("x")))


def test_unknown_body_version():
    with pytest.raises(InvalidBodyError) as exc:
        parse_body(2, doc(para(text("x"))))
    assert exc.value.errors[0]["loc"] == ["body_version"]
