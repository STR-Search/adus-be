"""Pydantic models for the comment body (Tiptap / ProseMirror JSON), version 1.

Writes are strict on *types*: an unknown node or mark ``type`` fails the
discriminated union (FE/BE drift). Unknown *attributes* and keys are ignored
and therefore dropped from the dump (editor noise such as mention ``label``
or link ``target``/``rel``/``class``). Containment rules are encoded in the
``content`` field types; list depth is enforced by the walker.
"""

from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from app.core.discussions.body.errors import InvalidBodyError

MAX_HREF_LENGTH = 2048
ALLOWED_LINK_SCHEMES = frozenset({"http", "https"})


def _reject_bool(value: Any) -> Any:
    # Pydantic's lax int mode turns True/False into 1/0; an id is never a bool.
    if isinstance(value, bool):
        raise ValueError("must be an integer, not a boolean")  # noqa: TRY004 (pydantic needs ValueError)
    return value


# Accepts 42 and "42"; rejects True, 42.5, "abc".
Int = Annotated[int, BeforeValidator(_reject_bool)]


class _Node(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ── Marks ────────────────────────────────────────────────────────────────────


class BoldMark(_Node):
    type: Literal["bold"]


class ItalicMark(_Node):
    type: Literal["italic"]


class StrikeMark(_Node):
    type: Literal["strike"]


class UnderlineMark(_Node):
    type: Literal["underline"]


class CodeMark(_Node):
    type: Literal["code"]


class LinkAttrs(_Node):
    href: str = Field(min_length=1, max_length=MAX_HREF_LENGTH)

    @field_validator("href")
    @classmethod
    def _http_only(cls, href: str) -> str:
        href = href.strip()
        parts = urlsplit(href)
        if parts.scheme.lower() not in ALLOWED_LINK_SCHEMES or not parts.netloc:
            raise ValueError("link href must be an absolute http(s) URL")
        return href


class LinkMark(_Node):
    type: Literal["link"]
    attrs: LinkAttrs


Mark = Annotated[
    BoldMark | ItalicMark | StrikeMark | UnderlineMark | CodeMark | LinkMark,
    Field(discriminator="type"),
]


# ── Inline nodes ─────────────────────────────────────────────────────────────


class TextNode(_Node):
    type: Literal["text"]
    # ProseMirror never emits empty text nodes.
    text: str = Field(min_length=1)
    marks: list[Mark] | None = None


class HardBreakNode(_Node):
    type: Literal["hardBreak"]


class MentionAttrs(_Node):
    # Only the id is kept; label/mentionSuggestionChar are dropped. Names are
    # resolved at read time from the users map, never stored in the body.
    id: Annotated[Int, Field(gt=0)]


class MentionNode(_Node):
    type: Literal["mention"]
    attrs: MentionAttrs


Inline = Annotated[
    TextNode | HardBreakNode | MentionNode,
    Field(discriminator="type"),
]


# ── Block nodes ──────────────────────────────────────────────────────────────


class ParagraphNode(_Node):
    type: Literal["paragraph"]
    # Tiptap omits ``content`` for an empty paragraph.
    content: list[Inline] | None = None


class ListItemNode(_Node):
    type: Literal["listItem"]
    content: list["Block"] = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _paragraph_then_lists(cls, content: list[Any]) -> list[Any]:
        if not isinstance(content[0], ParagraphNode):
            raise ValueError("listItem must start with a paragraph")  # noqa: TRY004
        if any(isinstance(child, ParagraphNode) for child in content[1:]):
            raise ValueError("listItem may only contain lists after its paragraph")
        return content


class BulletListNode(_Node):
    type: Literal["bulletList"]
    content: list[ListItemNode] = Field(min_length=1)


class OrderedListAttrs(_Node):
    start: Int = 1


class OrderedListNode(_Node):
    type: Literal["orderedList"]
    attrs: OrderedListAttrs = Field(default_factory=OrderedListAttrs)
    content: list[ListItemNode] = Field(min_length=1)


Block = Annotated[
    ParagraphNode | BulletListNode | OrderedListNode,
    Field(discriminator="type"),
]

ListNode = BulletListNode | OrderedListNode


class DocV1(_Node):
    type: Literal["doc"]
    content: list[Block] = Field(min_length=1)


ListItemNode.model_rebuild()


# ── Versions ─────────────────────────────────────────────────────────────────

CURRENT_BODY_VERSION = 1
BODY_SCHEMAS: dict[int, type[DocV1]] = {1: DocV1}


def parse_body(body_version: int, raw: Any) -> DocV1:
    """Validate a raw request body against the schema for ``body_version``.

    Raises ``InvalidBodyError`` with the failing paths.
    """
    schema = BODY_SCHEMAS.get(body_version)
    if schema is None:
        raise InvalidBodyError(
            f"Unsupported body_version: {body_version}",
            [
                {
                    "loc": ["body_version"],
                    "msg": f"must be one of {sorted(BODY_SCHEMAS)}",
                    "type": "value_error",
                }
            ],
        )
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        raise InvalidBodyError(
            "Invalid comment body",
            [
                {"loc": ["body", *err["loc"]], "msg": err["msg"], "type": err["type"]}
                for err in exc.errors(include_url=False, include_input=False)
            ],
        ) from exc
