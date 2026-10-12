"""Traversals of a comment body.

``enforce_limits`` scans the *raw* request JSON before Pydantic parses it, so
an oversized or deeply nested payload is rejected without building models.
It is deliberately tolerant of malformed shapes (it skips what it does not
recognise); rejecting bad shapes is the parser's job.

``walk`` / ``analyze`` run on the *parsed* document and yield the facts that
need validated nodes: the mention ids and whether the comment is empty.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.core.discussions.body.errors import InvalidBodyError
from app.core.discussions.body.nodes import DocV1, MentionNode, TextNode

MAX_TEXT_CHARS = 10_000
MAX_NODES = 1_000
MAX_DISTINCT_MENTIONS = 20
MAX_LIST_DEPTH = 3
# doc(0) → (list → listItem) × MAX_LIST_DEPTH → paragraph → inline. Anything
# deeper is invalid anyway; stopping here bounds the parser's recursion.
MAX_NODE_DEPTH = 2 * MAX_LIST_DEPTH + 2

_RAW_LIST_TYPES = frozenset({"bulletList", "orderedList"})


# ── Pre-parse limits (raw JSON) ──────────────────────────────────────────────


def enforce_limits(raw: Any) -> None:
    """Raise ``InvalidBodyError`` as soon as the raw body exceeds a limit.

    Follows ``content`` arrays only. Counts every node (marks excluded), the
    length of every string ``text``, distinct mention ids (``42`` and ``"42"``
    count once), list nesting, and node depth.
    """
    if not isinstance(raw, dict):
        return  # the parser reports the shape error

    node_count = 0
    text_chars = 0
    mention_ids: set[Any] = set()
    # (node, node depth, list depth including this node)
    stack: list[tuple[dict, int, int]] = [(raw, 0, 0)]

    while stack:
        node, depth, list_depth = stack.pop()

        node_count += 1
        if node_count > MAX_NODES:
            raise InvalidBodyError(f"body exceeds {MAX_NODES} nodes")
        if depth > MAX_NODE_DEPTH:
            raise InvalidBodyError(f"body nests deeper than {MAX_NODE_DEPTH} nodes")
        if list_depth > MAX_LIST_DEPTH:
            raise InvalidBodyError(f"lists nest deeper than {MAX_LIST_DEPTH}")

        text = node.get("text")
        if isinstance(text, str):
            text_chars += len(text)
            if text_chars > MAX_TEXT_CHARS:
                raise InvalidBodyError(f"text exceeds {MAX_TEXT_CHARS} characters")

        if node.get("type") == "mention":
            mention_ids.add(_mention_key(node))
            if len(mention_ids) > MAX_DISTINCT_MENTIONS:
                raise InvalidBodyError(
                    f"body mentions more than {MAX_DISTINCT_MENTIONS} users"
                )

        content = node.get("content")
        if isinstance(content, list):
            for child in content:
                if isinstance(child, dict):
                    is_list = child.get("type") in _RAW_LIST_TYPES
                    stack.append((child, depth + 1, list_depth + is_list))


def _mention_key(node: dict) -> Any:
    attrs = node.get("attrs")
    value = attrs.get("id") if isinstance(attrs, dict) else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    # Unhashable or odd ids are invalid; the parser rejects them. Count once.
    return value if isinstance(value, int | str | None) else repr(value)


# ── Post-parse facts (validated document) ────────────────────────────────────


def walk(doc: DocV1) -> Iterator[BaseModel]:
    """Pre-order, document-order traversal of every node (marks excluded)."""
    stack: list[BaseModel] = [doc]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(getattr(node, "content", None) or []))


@dataclass(frozen=True, slots=True)
class BodyFacts:
    # Distinct, in order of first appearance.
    mention_ids: tuple[int, ...]
    # Non-whitespace text or at least one mention.
    has_content: bool


def analyze(doc: DocV1) -> BodyFacts:
    mention_ids: dict[int, None] = {}
    has_content = False
    for node in walk(doc):
        if isinstance(node, TextNode):
            has_content = has_content or not node.text.isspace()
        elif isinstance(node, MentionNode):
            mention_ids.setdefault(node.attrs.id)
            has_content = True
    return BodyFacts(mention_ids=tuple(mention_ids), has_content=has_content)


def reject_empty(facts: BodyFacts) -> None:
    if not facts.has_content:
        raise InvalidBodyError("comment is empty")
