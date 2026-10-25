from enum import StrEnum


class SubjectType(StrEnum):
    """What a transition or snapshot is about.

    Plain text in the DB (no CHECK), so adding a subject never alters a table.
    """

    UNDERWRITING = "underwriting"


class Flow(StrEnum):
    """Which status machine of a subject. Plain text in the DB (no CHECK)."""

    DEAL_STATUS = "deal_status"


class TransitionSource(StrEnum):
    """What caused a transition. A closed set, CHECK-constrained in the DB."""

    API = "api"
    JOB = "job"
    BACKFILL = "backfill"
    SYSTEM = "system"
