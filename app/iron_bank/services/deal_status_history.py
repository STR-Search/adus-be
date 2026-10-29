"""The underwriting side of the ``deal_status`` process log.

iron_bank owns what an underwriting snapshot contains; ``app.core.process_log``
only stores and dedupes it. Design: ``docs/features/process_log/process_log.md``.
"""

from collections.abc import Mapping
from typing import Any

from app.core.process_log.enums import Flow, SubjectType, TransitionSource
from app.core.process_log.schemas import SnapshotInput
from app.core.process_log.service import ProcessLogService
from app.iron_bank.models.underwriting import Underwriting
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.get_underwriting import (
    GetUnderwritingCompSet,
    GetUnderwritingDetails,
    GetUnderwritingOperatingExpense,
    GetUnderwritingOptimizationItem,
    GetUnderwritingResult,
    GetUnderwritingTaxes,
)
from app.iron_bank.schemas.underwriting import UnderwritingRead

# Bump when the payload's shape changes; stored rows are never rewritten.
UNDERWRITING_SNAPSHOT_VERSION = 1

# Fields of GetUnderwritingResult that are resolved from other tables or set by
# a particular read path, not stored on the deal. Left out so a snapshot changes
# only when the deal does (a renamed realtor or user must not look like a deal
# change), and no names/emails are copied into the append-only log. Tag labels
# (every ``*_label`` field) are excluded the same way; their slugs are kept.
_UNRESOLVED_EXCLUDE: frozenset[str] = frozenset(
    {
        "analyst",
        "approver",
        "owner",
        "realtor_details",
        "simulated",
        "discussion",
        "display_id",
    }
)


def underwriting_document(underwriting: Underwriting) -> dict[str, Any]:
    """The deal's own data in ``GetUnderwritingResult`` shape: parent row plus
    child tables, with nothing resolved from other tables.

    Shared by the n8n webhook (which adds users, realtors, live zillow data and
    labels on top) and the process-log snapshot (which uses it as is), so both
    carry the same structure. The children must already be loaded.
    """
    document: dict[str, Any] = {
        field: value
        for field in UnderwritingRead.model_fields
        if (value := getattr(underwriting, field, None)) is not None
    }
    if detail := getattr(underwriting, "detail", None):
        document["details"] = GetUnderwritingDetails.model_validate(detail)
    if taxes := getattr(underwriting, "taxes", None):
        document["taxes"] = GetUnderwritingTaxes.model_validate(taxes)
    if optimization_items := getattr(underwriting, "optimization_items", None):
        document["optimization_list"] = [
            GetUnderwritingOptimizationItem.model_validate(item)
            for item in optimization_items
        ]
    if operating_expenses := getattr(underwriting, "operating_expenses", None):
        document["operating_expenses"] = [
            GetUnderwritingOperatingExpense.model_validate(item)
            for item in operating_expenses
        ]
    if comp_set := getattr(underwriting, "comp_set", None):
        document["comp_set"] = [
            GetUnderwritingCompSet.model_validate(item) for item in comp_set
        ]
    return document


def build_underwriting_snapshot(underwriting: Underwriting) -> SnapshotInput:
    """The full deal (row + children) as JSON, minus resolved fields.

    ``mode="json"`` renders Decimals as strings ("525000.00"), as the webhook
    does, so equal deals always hash equally.
    """
    payload = GetUnderwritingResult.model_validate(
        underwriting_document(underwriting)
    ).model_dump(mode="json")
    return SnapshotInput(
        schema_version=UNDERWRITING_SNAPSHOT_VERSION,
        payload={
            key: value
            for key, value in payload.items()
            if key not in _UNRESOLVED_EXCLUDE and not key.endswith("_label")
        },
    )


async def record_created(
    process_log: ProcessLogService,
    repository: UnderwritingRepository,
    underwriting: Underwriting,
    *,
    source: TransitionSource,
    actor_user_id: int | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Write the head row of a new underwriting's ``deal_status`` chain.

    Call after ``repository.create(..., commit=False)`` and before committing.
    A NULL status starts no chain; the first status set later becomes the head.
    """
    if underwriting.deal_status is None:
        return
    await repository.load_children(underwriting)
    await process_log.record_transition(
        subject_type=SubjectType.UNDERWRITING,
        subject_id=underwriting.id,
        flow=Flow.DEAL_STATUS,
        expected_from_status=None,
        to_status=underwriting.deal_status,
        source=source,
        actor_user_id=actor_user_id,
        metadata=metadata,
        snapshot=build_underwriting_snapshot(underwriting),
    )
