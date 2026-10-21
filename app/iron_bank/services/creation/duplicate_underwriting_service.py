from typing import Any

import structlog
from sqlalchemy import JSON, null
from sqlalchemy.exc import IntegrityError

from app.iron_bank.enums import DealStatus, UnderwritingSource
from app.iron_bank.models import (
    Underwriting,
    UnderwritingCompSet,
    UnderwritingDetail,
    UnderwritingOperatingExpense,
    UnderwritingOptimizationItem,
    UnderwritingTax,
)
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.duplicate_underwriting import DuplicateUnderwritingResult

logger = structlog.get_logger(__name__)

_SERIES_VERSION_CONSTRAINT = "uq_underwritings_series_version"

# Columns NOT carried over to the copy. Everything else on the table is copied,
# deliberately: deriving the copy from ``__table__.columns`` minus this set means
# a column added to Underwriting later is copied by default, instead of being
# silently dropped by a hand-maintained include-list nobody remembers to update.
# The test suite asserts this set is the only difference between a row and its
# copy, so adding a column is a decision, not an accident.
_UNDERWRITING_NON_COPYABLE: frozenset[str] = frozenset(
    {
        # Identity and lineage — assigned explicitly below.
        "id",
        "series_id",
        "version",
        "copied_from_id",
        # Timestamps. deal_added is omitted rather than nulled so its server
        # default stamps the copy's own creation time.
        "created_at",
        "updated_at",
        "deal_added",
        "deal_submitted",
        "deal_approved",
        # People. owner_id IS copied — ownership is a market-level fact that
        # survives duplication; analyst/approver are per-underwriting work
        # assignments and do not.
        "analyst_id",
        "approver_id",
        # Workflow state. Copying deal_status is actively unsafe: the terminal
        # statuses (client_under_contract, delete_deal, ...) have empty
        # transition sets in DEAL_STATUS_TRANSITIONS, so a copy inheriting one
        # would be frozen and unusable from birth.
        "deal_status",
        "deal_score",
        # Provenance. A copy of a backfilled sheet row is not itself a sheet
        # row, and sheet_number is partial-unique so copying it would fail.
        "source",
        "sheet_number",
        # NOTE: is_automated is deliberately NOT here. It reads like a
        # provenance label ("was this hand-made?"), and forcing it to False on a
        # copy looks obviously right — but it is really a *hydration path*
        # selector. GetUnderwritingService.get_edit_context, that service's list
        # enrichment, and UpdateUnderwritingService._hydrate_zillow_property all
        # branch on it: True reads zillow live from scheduled_listings by zpid,
        # False reads the snapshot stored on uw_details.zillow_property. The
        # automated builder never writes that snapshot (only
        # NonAutomatedUnderwritingPayloadBuilder does), so an automated row has
        # a zpid and no snapshot. Flipping the flag on its copy would send the
        # copy down the stored-snapshot branch, find NULL, and show no zillow
        # data at all — the zpid is right there but nothing falls back to it.
        # Copying the flag keeps each copy on its source's working path.
        # "This copy was made by hand" is expressed by copied_from_id/version.
        # Narrative and client-facing artifacts belong to the version that
        # produced them, not to a fresh fork of its numbers.
        "deal_pitch",
        "note",
        "loom_vid",
        "video_walkthrough",
        "survey",
    }
)

# Child rows are re-parented and re-ordered by the repository on insert.
# sort_order must be excluded as well as id: ``UnderwritingRepository.create``
# passes ``sort_order=index`` positionally alongside ``**item``, so leaving it in
# the dict raises TypeError on the duplicate keyword. Collection order is already
# the stored sort order (the relationships order by it), so position carries it.
_CHILD_NON_COPYABLE: frozenset[str] = frozenset(
    {"id", "underwriting_id", "sort_order"}
)
_SINGLETON_NON_COPYABLE: frozenset[str] = frozenset({"id", "underwriting_id"})


def _copy_columns(instance: Any, model: Any, exclude: frozenset[str]) -> dict[str, Any]:
    """Column values of ``instance``, minus ``exclude``.

    Reads ``model.__table__.columns`` rather than the instance's ``__dict__`` so
    unloaded attributes and the ``column_property`` aggregates
    (optimization_total / operating_expense_total, which are correlated
    subqueries and not table columns) are both excluded automatically.

    A NULL JSON column is copied as SQL NULL, not as the JSON value ``null``.
    SQLAlchemy's JSON/JSONB types default to ``none_as_null=False``, so handing
    them a plain Python ``None`` writes the JSON scalar ``'null'`` instead — the
    two read back identically in Python but are not the same to Postgres, and
    ``WHERE col IS NULL`` silently stops matching the copy. ``null()`` forces
    the SQL form so the fork matches its source at the DB level too.
    """
    values: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name in exclude:
            continue
        value = getattr(instance, column.name)
        if value is None and isinstance(column.type, JSON):
            value = null()
        values[column.name] = value
    return values


def _is_series_version_conflict(error: IntegrityError) -> bool:
    return _SERIES_VERSION_CONSTRAINT in str(getattr(error, "orig", error))


class DuplicateUnderwritingService:
    """Forks an underwriting into the next version of its series.

    Deliberately does not go through ``SaveUnderwritingService``: that path
    recalculates derived metrics from current market data, which would produce a
    copy whose numbers differ from the original it claims to duplicate. This is a
    faithful, offline fork — no network calls, no recalculation, no webhook. The
    source row's values were already validated when it was saved.
    """

    _MAX_VERSION_ATTEMPTS = 3

    def __init__(self, repository: UnderwritingRepository):
        self.repository = repository

    async def duplicate(
        self,
        *,
        underwriting_id: int,
        current_user_id: int | None = None,
    ) -> DuplicateUnderwritingResult:
        source = await self.repository.get_by_id(underwriting_id)
        if source is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        # Everything read off ``source`` is captured into plain Python values
        # BEFORE the retry loop, and nothing below reads the instance again.
        # ``repository.create`` rolls the shared session back when an insert
        # fails, and ``Session.rollback()`` expires every loaded ORM instance —
        # so a post-rollback ``source.id`` would trigger a synchronous lazy
        # refresh and raise MissingGreenlet under asyncio, turning a retryable
        # version conflict into a hard 500.
        source_id = source.id
        series_id = source.series_id

        underwriting_data = _copy_columns(
            source, Underwriting, _UNDERWRITING_NON_COPYABLE
        )
        underwriting_data.update(
            {
                # The copy joins its source's family rather than starting one.
                "series_id": series_id,
                # The row actually duplicated, which for a copy-of-a-copy is the
                # copy — not the series original.
                "copied_from_id": source_id,
                "analyst_id": current_user_id,
                "approver_id": None,
                "deal_status": DealStatus.TEMPLATE_GENERATED.value,
                "source": UnderwritingSource.ADUS.value,
                "sheet_number": None,
                "deal_score": None,
            }
        )

        detail_data = (
            _copy_columns(source.detail, UnderwritingDetail, _SINGLETON_NON_COPYABLE)
            if source.detail is not None
            else None
        )
        tax_data = (
            _copy_columns(source.taxes, UnderwritingTax, _SINGLETON_NON_COPYABLE)
            if source.taxes is not None
            else None
        )
        optimization_items = [
            _copy_columns(item, UnderwritingOptimizationItem, _CHILD_NON_COPYABLE)
            for item in source.optimization_items
        ]
        operating_expenses = [
            _copy_columns(item, UnderwritingOperatingExpense, _CHILD_NON_COPYABLE)
            for item in source.operating_expenses
        ]
        comp_set = [
            _copy_columns(item, UnderwritingCompSet, _CHILD_NON_COPYABLE)
            for item in source.comp_set
        ]

        for attempt in range(self._MAX_VERSION_ATTEMPTS):
            underwriting_data["version"] = (
                await self.repository.get_next_version_for_series(series_id)
            )
            try:
                created = await self.repository.create(
                    underwriting_data,
                    detail_data=detail_data,
                    tax_data=tax_data,
                    optimization_items=optimization_items,
                    operating_expenses=operating_expenses,
                    comp_set=comp_set,
                )
            except IntegrityError as error:
                # Another duplicate of the same series claimed this version
                # number between our max() read and our insert. The repository
                # has already rolled back, so re-reading the max on the next
                # pass runs on a clean session.
                if (
                    not _is_series_version_conflict(error)
                    or attempt == self._MAX_VERSION_ATTEMPTS - 1
                ):
                    raise
                logger.info(
                    "iron_bank.duplicate_underwriting.version_conflict_retry",
                    source_underwriting_id=source_id,
                    attempted_version=underwriting_data["version"],
                    attempt=attempt,
                )
                continue

            logger.info(
                "iron_bank.duplicate_underwriting.created",
                source_underwriting_id=source_id,
                underwriting_id=created.id,
                series_id=str(created.series_id),
                version=created.version,
            )
            return DuplicateUnderwritingResult(
                underwriting_id=created.id,
                series_id=created.series_id,
                version=created.version,
                copied_from_id=source_id,
            )

        # Unreachable: the final attempt either returns or re-raises above. Kept
        # so a future change to the loop bounds fails loudly rather than
        # returning None.
        raise RuntimeError(
            "Exhausted version assignment retries duplicating underwriting "
            f"{source_id}"
        )
