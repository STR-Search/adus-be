"""The full write-path pipeline for a comment body (create and edit)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.core.discussions.body.errors import InvalidMentionError
from app.core.discussions.body.nodes import parse_body
from app.core.discussions.body.text import derive_body_text
from app.core.discussions.body.walker import analyze, enforce_limits, reject_empty
from app.core.discussions.interfaces import UserLookup, UserRef


@dataclass(frozen=True, slots=True)
class ProcessedBody:
    body: dict[str, Any]  # normalized; this is what gets stored, not the request
    body_text: str
    mention_user_ids: tuple[int, ...]
    # The mentioned users, already resolved; saves the caller a second lookup.
    users: Mapping[int, UserRef]


async def process_body(
    body_version: int, raw: Any, user_lookup: UserLookup
) -> ProcessedBody:
    """Check limits, parse, reject empty, resolve mentions, derive text.

    Limits run on the raw JSON first, so oversized payloads never reach the
    parser. Raises ``InvalidBodyError`` or ``InvalidMentionError``. Mentions
    are never dropped silently: any unknown or soft-deleted user fails the
    whole body.
    """
    enforce_limits(raw)
    doc = parse_body(body_version, raw)
    facts = analyze(doc)
    reject_empty(facts)

    users = await user_lookup.get_users(facts.mention_ids) if facts.mention_ids else {}
    invalid = [
        user_id
        for user_id in facts.mention_ids
        if user_id not in users or users[user_id].is_deleted
    ]
    if invalid:
        raise InvalidMentionError(invalid)

    return ProcessedBody(
        body=doc.model_dump(exclude_none=True),
        body_text=derive_body_text(doc, users),
        mention_user_ids=facts.mention_ids,
        users=users,
    )
