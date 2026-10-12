from app.core.discussions.body.nodes import parse_body
from app.core.discussions.body.text import derive_body_text, mention_label
from app.core.discussions.interfaces import UserRef
from tests.core.discussions.conftest import (
    JANE,
    SAM,
    bullets,
    doc,
    item,
    mention,
    ordered,
    para,
    text,
)

USERS = {SAM.id: SAM, JANE.id: JANE}
HARD_BREAK = {"type": "hardBreak"}


def render(raw, users=USERS):
    return derive_body_text(parse_body(1, raw), users)


def test_paragraphs_and_mentions():
    raw = doc(
        para(
            text("ADR looks high, "),
            mention(42),
            text("."),
            HARD_BREAK,
            text("Agreed?"),
        ),
        para(),
        para(text("cc "), mention(7, label="stale label")),
    )
    assert render(raw) == "ADR looks high, @Jane Doe.\nAgreed?\n\ncc @Sam Lee"


def test_marks_do_not_affect_text():
    raw = doc(para(text("bold", marks=[{"type": "bold"}]), text(" plain")))
    assert render(raw) == "bold plain"


def test_lists():
    raw = doc(
        para(text("Notes:")),
        bullets(
            item(para(text("Occupancy fine"))),
            item(
                para(text("ADR"), HARD_BREAK, text("too high")),
                ordered(
                    item(para(text("comp A")), bullets(item(para(text("deep"))))),
                    item(para(text("comp B"))),
                    start=3,
                ),
            ),
        ),
        ordered(item(para(text("first"))), item(para(text("second")))),
    )
    assert render(raw).split("\n") == [
        "Notes:",
        "- Occupancy fine",
        "- ADR",
        "  too high",
        "  3. comp A",
        "    - deep",
        "  4. comp B",
        "1. first",
        "2. second",
    ]


def test_mention_label_fallbacks():
    assert mention_label(UserRef(1, "Sam", None, "s@x.com", False)) == "@Sam"
    assert mention_label(UserRef(1, None, " Lee ", None, False)) == "@Lee"
    assert mention_label(UserRef(1, "  ", None, "s@x.com", False)) == "@s@x.com"
    assert mention_label(UserRef(1, None, None, None, False)) == "@unknown"
    assert mention_label(None) == "@unknown"


def test_unresolved_mention_renders_unknown():
    assert render(doc(para(mention(5))), users={}) == "@unknown"
