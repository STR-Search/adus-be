from enum import StrEnum


class SubjectType(StrEnum):
    """What a thread is about. Stored on ``threads.subject_type``; set once.

    Plain text in the DB (no CHECK), so adding a subject never alters a table.
    """

    UNDERWRITING = "underwriting"


class ThreadKind(StrEnum):
    """Which thread of a subject. Stored on each domain's link table ``kind``."""

    GENERAL = "general"
