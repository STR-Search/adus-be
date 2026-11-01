from collections.abc import Sequence
from datetime import date

from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.analytics.schemas import Granularity
from app.core.process_log.enums import Flow, SubjectType, TransitionSource
from app.core.process_log.models import Transition
from app.core.query_filters import date_range_conditions
from app.iron_bank.enums import DealStatus
from app.iron_bank.models import Underwriting
from app.iron_bank.repositories.underwriting_analytics_repository import (
    period_column,
    status_in,
    underwriting_filter_conditions,
)
from app.iron_bank.schemas.underwriting_analytics import UnderwritingAnalyticsFilters
from app.users.models.user import User

_SECONDS_PER_DAY = 86_400

# (key, lower inclusive, upper exclusive) in days; None = open end.
AgeBucketBounds = Sequence[tuple[str, int | None, int | None]]


def deal_status_rows():
    """Conditions selecting underwriting deal_status rows of the process log."""
    return (
        Transition.subject_type == SubjectType.UNDERWRITING.value,
        Transition.flow == Flow.DEAL_STATUS.value,
    )


def observed():
    """A logged change, not a row the backfill seeded from current state."""
    return Transition.source != TransitionSource.BACKFILL.value


def _days(interval):
    return func.extract("epoch", interval) / _SECONDS_PER_DAY


class StatusHistoryAnalyticsRepository:
    """Read-only queries joining ``process_log.transitions`` to underwritings.

    Backfill rows only say "was in this status as of this date", so anything
    that times or attributes a change leaves them out.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def backlog_age(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        statuses: Sequence[DealStatus],
        buckets: AgeBucketBounds,
        group_by_status: bool,
    ) -> list[dict]:
        """Per status (or one overall row): how long deals have sat in it.

        A deal's wait starts at its latest log row when that row matches its
        current status; otherwise (no history, or the status was changed
        outside the log) at ``updated_at``, then ``created_at``. Rows have
        ``deal_status`` (None overall), ``deals``, one count per bucket key,
        ``observed``, ``median_days`` and ``measured``.
        """
        latest = (
            select(
                Transition.subject_id,
                Transition.to_status,
                Transition.occurred_at,
                Transition.source,
            )
            .where(*deal_status_rows())
            .distinct(Transition.subject_id)
            # Within a chain, id order is chain order.
            .order_by(Transition.subject_id, Transition.id.desc())
            .subquery()
        )
        in_step = latest.c.to_status == Underwriting.deal_status
        since = case(
            (in_step, latest.c.occurred_at),
            else_=func.coalesce(Underwriting.updated_at, Underwriting.created_at),
        )
        age = _days(func.now() - since)
        measures = [
            func.count().label("deals"),
            *(
                func.count().filter(*_bucket_conditions(age, lower, upper)).label(key)
                for key, lower, upper in buckets
            ),
            func.count()
            .filter(in_step, latest.c.source != TransitionSource.BACKFILL.value)
            .label("observed"),
            func.percentile_cont(0.5).within_group(age).label("median_days"),
            func.count(age).label("measured"),
        ]
        columns = [Underwriting.deal_status, *measures] if group_by_status else measures
        query = (
            select(*columns)
            .select_from(Underwriting)
            .outerjoin(latest, latest.c.subject_id == Underwriting.id)
            .where(*underwriting_filter_conditions(filters), status_in(statuses))
        )
        if group_by_status:
            query = query.group_by(Underwriting.deal_status)
        result = await self.db.execute(query)
        rows = [dict(row._mapping) for row in result.all()]
        if not group_by_status:
            for row in rows:
                row["deal_status"] = None
        return rows

    async def time_to_present(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        presented_from: date | None = None,
        presented_to: date | None = None,
    ) -> dict:
        """Days from ``deal_added`` to the deal's first known presentation.

        The presentation time is the earlier of the first logged change to
        present_to_clients and ``deal_approved``: the log for deals presented
        since it shipped, ``deal_approved`` for deals presented before. Deals
        whose presentation predates ``deal_added`` (bad legacy dates) are left
        out. Returns ``median_days``, ``p75_days``, ``measured``, ``observed``.
        """
        first_logged = (
            select(
                Transition.subject_id,
                func.min(Transition.occurred_at).label("presented_at"),
            )
            .where(
                *deal_status_rows(),
                observed(),
                Transition.to_status == DealStatus.PRESENT_TO_CLIENTS.value,
            )
            .group_by(Transition.subject_id)
            .subquery()
        )
        # LEAST ignores NULLs, so either source alone is enough.
        presented_at = func.least(
            first_logged.c.presented_at, Underwriting.deal_approved
        )
        days = _days(presented_at - Underwriting.deal_added)
        query = (
            select(
                func.percentile_cont(0.5).within_group(days).label("median_days"),
                func.percentile_cont(0.75).within_group(days).label("p75_days"),
                func.count().label("measured"),
                func.count()
                .filter(first_logged.c.presented_at == presented_at)
                .label("observed"),
            )
            .select_from(Underwriting)
            .outerjoin(first_logged, first_logged.c.subject_id == Underwriting.id)
            .where(
                *underwriting_filter_conditions(filters),
                presented_at.is_not(None),
                Underwriting.deal_added.is_not(None),
                presented_at >= Underwriting.deal_added,
                *date_range_conditions(presented_at, presented_from, presented_to),
            )
        )
        return dict((await self.db.execute(query)).one()._mapping)

    async def moved_to_by_actor(
        self,
        filters: UnderwritingAnalyticsFilters,
        statuses: Sequence[DealStatus],
        *,
        occurred_from: date | None = None,
        occurred_to: date | None = None,
    ) -> list[tuple[int | None, str, int]]:
        """``(actor_user_id, to_status, distinct deals)`` from logged changes."""
        query = (
            select(
                Transition.actor_user_id,
                Transition.to_status,
                func.count(distinct(Transition.subject_id)),
            )
            .join(Underwriting, Underwriting.id == Transition.subject_id)
            .where(*self._moved_to(filters, statuses, occurred_from, occurred_to))
            .group_by(Transition.actor_user_id, Transition.to_status)
        )
        result = await self.db.execute(query)
        return [(actor, status, count) for actor, status, count in result.all()]

    async def moved_to_by_actor_and_period(
        self,
        filters: UnderwritingAnalyticsFilters,
        status: DealStatus,
        granularity: Granularity,
        *,
        occurred_from: date | None = None,
        occurred_to: date | None = None,
    ) -> list[tuple[int | None, date, int]]:
        """``(actor_user_id, period_start, distinct deals)`` moved to ``status``."""
        period = period_column(Transition.occurred_at, granularity)
        query = (
            select(
                Transition.actor_user_id,
                period,
                func.count(distinct(Transition.subject_id)),
            )
            .join(Underwriting, Underwriting.id == Transition.subject_id)
            .where(*self._moved_to(filters, (status,), occurred_from, occurred_to))
            .group_by(Transition.actor_user_id, period)
        )
        result = await self.db.execute(query)
        return [(actor, start, count) for actor, start, count in result.all()]

    async def approval_outcomes(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        approved: Sequence[DealStatus],
        rejected: Sequence[DealStatus],
        completed_from: date | None = None,
        completed_to: date | None = None,
    ) -> list[tuple[int | None, str, int]]:
        """``(analyst, outcome, deals)`` for deals moved to analyst_completed.

        Each deal counts once, under whoever made its first logged completion
        in the range. ``outcome`` is ``approved`` when a later change moved it
        to an ``approved`` status, else ``rejected`` when it now sits in a
        ``rejected`` status, else ``pending``.
        """
        completed = (
            select(
                Transition.id,
                Transition.subject_id,
                Transition.actor_user_id,
            )
            .where(
                *deal_status_rows(),
                observed(),
                Transition.to_status == DealStatus.ANALYST_COMPLETED.value,
                *date_range_conditions(
                    Transition.occurred_at, completed_from, completed_to
                ),
            )
            .distinct(Transition.subject_id)
            .order_by(Transition.subject_id, Transition.id)
            .subquery()
        )
        later = aliased(Transition)
        was_approved = (
            select(later.id)
            .where(
                later.subject_type == SubjectType.UNDERWRITING.value,
                later.flow == Flow.DEAL_STATUS.value,
                later.subject_id == completed.c.subject_id,
                # Chain order is id order, so "later" is a higher id.
                later.id > completed.c.id,
                later.to_status.in_([s.value for s in approved]),
            )
            .exists()
        )
        outcome = case(
            (was_approved, "approved"),
            (status_in(rejected), "rejected"),
            else_="pending",
        ).label("outcome")
        query = (
            select(completed.c.actor_user_id, outcome, func.count())
            .join(Underwriting, Underwriting.id == completed.c.subject_id)
            .where(*underwriting_filter_conditions(filters))
            .group_by(completed.c.actor_user_id, outcome)
        )
        result = await self.db.execute(query)
        return [(actor, kind, count) for actor, kind, count in result.all()]

    async def approval_wait(
        self,
        filters: UnderwritingAnalyticsFilters,
        *,
        group_by_approver: bool,
        presented_from: date | None = None,
        presented_to: date | None = None,
    ) -> list[dict]:
        """Days from the last analyst_completed to the first present_to_clients.

        Both changes must be logged ones, so only deals presented since the
        history started count. Rows have ``approver`` (None overall),
        ``median_days``, ``p75_days`` and ``deals``.
        """
        presented = (
            select(
                Transition.id,
                Transition.subject_id,
                Transition.actor_user_id,
                Transition.occurred_at,
            )
            .where(
                *deal_status_rows(),
                observed(),
                Transition.to_status == DealStatus.PRESENT_TO_CLIENTS.value,
            )
            .distinct(Transition.subject_id)
            .order_by(Transition.subject_id, Transition.id)
            .subquery()
        )
        completion = aliased(Transition)
        completed_at = (
            select(func.max(completion.occurred_at))
            .where(
                completion.subject_type == SubjectType.UNDERWRITING.value,
                completion.flow == Flow.DEAL_STATUS.value,
                completion.subject_id == presented.c.subject_id,
                completion.source != TransitionSource.BACKFILL.value,
                completion.to_status == DealStatus.ANALYST_COMPLETED.value,
                completion.id < presented.c.id,
            )
            .scalar_subquery()
        )
        days = _days(presented.c.occurred_at - completed_at)
        measures = [
            func.percentile_cont(0.5).within_group(days).label("median_days"),
            func.percentile_cont(0.75).within_group(days).label("p75_days"),
            func.count(days).label("deals"),
        ]
        columns = (
            [presented.c.actor_user_id.label("approver"), *measures]
            if group_by_approver
            else measures
        )
        query = (
            select(*columns)
            .select_from(presented)
            .join(Underwriting, Underwriting.id == presented.c.subject_id)
            .where(
                *underwriting_filter_conditions(filters),
                completed_at.is_not(None),
                *date_range_conditions(
                    presented.c.occurred_at, presented_from, presented_to
                ),
            )
        )
        if group_by_approver:
            query = query.group_by(presented.c.actor_user_id)
        result = await self.db.execute(query)
        rows = [dict(row._mapping) for row in result.all()]
        if not group_by_approver:
            for row in rows:
                row["approver"] = None
        return rows

    async def user_names(self, user_ids: Sequence[int]) -> dict[int, str]:
        """Display names for ``user_ids``; users without a name are left out."""
        if not user_ids:
            return {}
        query = select(User.id, User.first_name, User.last_name, User.email).where(
            User.id.in_(user_ids)
        )
        names = {}
        for user_id, first, last, email in (await self.db.execute(query)).all():
            name = " ".join(part for part in (first, last) if part) or email
            if name:
                names[user_id] = name
        return names

    @staticmethod
    def _moved_to(
        filters: UnderwritingAnalyticsFilters,
        statuses: Sequence[DealStatus],
        occurred_from: date | None,
        occurred_to: date | None,
    ) -> list:
        return [
            *deal_status_rows(),
            observed(),
            Transition.to_status.in_([s.value for s in statuses]),
            *underwriting_filter_conditions(filters),
            *date_range_conditions(Transition.occurred_at, occurred_from, occurred_to),
        ]


def _bucket_conditions(age, lower: int | None, upper: int | None) -> list:
    conditions = []
    if lower is not None:
        conditions.append(age >= lower)
    if upper is not None:
        conditions.append(age < upper)
    return conditions
