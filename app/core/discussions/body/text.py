"""Plain-text rendering of a body, stored as ``comments.body_text``.

Lines are joined with ``\\n`` (no trailing newline): one line per paragraph,
``hardBreak`` starts a new line, list items are prefixed ``- `` / ``N. `` and
indented two spaces per nesting level. Mentions render as ``@First Last``,
falling back to ``@email`` and then ``@unknown``.
"""

from collections.abc import Mapping

from app.core.discussions.body.nodes import (
    DocV1,
    HardBreakNode,
    ListItemNode,
    ListNode,
    MentionNode,
    OrderedListNode,
    ParagraphNode,
    TextNode,
)
from app.core.discussions.interfaces import UserRef

INDENT = "  "


def mention_label(user: UserRef | None) -> str:
    if user is not None:
        name = " ".join(
            p.strip() for p in (user.first_name, user.last_name) if p and p.strip()
        )
        if name:
            return f"@{name}"
        if user.email and user.email.strip():
            return f"@{user.email.strip()}"
    return "@unknown"


def derive_body_text(doc: DocV1, users: Mapping[int, UserRef]) -> str:
    lines: list[str] = []
    for block in doc.content:
        if isinstance(block, ParagraphNode):
            lines.extend(_paragraph_lines(block, users))
        else:
            _render_list(block, 0, users, lines)
    return "\n".join(lines)


def _paragraph_lines(
    paragraph: ParagraphNode, users: Mapping[int, UserRef]
) -> list[str]:
    parts: list[str] = []
    for node in paragraph.content or []:
        if isinstance(node, TextNode):
            parts.append(node.text)
        elif isinstance(node, MentionNode):
            parts.append(mention_label(users.get(node.attrs.id)))
        elif isinstance(node, HardBreakNode):
            parts.append("\n")
    return "".join(parts).split("\n")


def _render_list(
    node: ListNode, depth: int, users: Mapping[int, UserRef], lines: list[str]
) -> None:
    start = node.attrs.start if isinstance(node, OrderedListNode) else 0
    for index, item in enumerate(node.content):
        marker = f"{start + index}. " if isinstance(node, OrderedListNode) else "- "
        _render_item(item, marker, depth, users, lines)


def _render_item(
    item: ListItemNode,
    marker: str,
    depth: int,
    users: Mapping[int, UserRef],
    lines: list[str],
) -> None:
    indent = INDENT * depth
    paragraph, *nested = item.content
    first, *rest = _paragraph_lines(paragraph, users)
    lines.append(f"{indent}{marker}{first}")
    # Continuation lines from hard breaks align under the item's text.
    lines.extend(f"{indent}{' ' * len(marker)}{line}" for line in rest)
    # ListItemNode guarantees everything after the paragraph is a list.
    for child in nested:
        _render_list(child, depth + 1, users, lines)
