from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.models import UnderwritingThread


class UnderwritingThreadRepository:
    """iron_bank's link table to discussion threads.

    Touches only ``iron_bank.underwriting_threads``; never joins discussion
    tables (see the layering rule in docs/underwriting_discussions.md §1).
    Never commits: it takes part in the caller's comment transaction.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_thread_id(self, underwriting_id: int, kind: str) -> int | None:
        return await self.db.scalar(
            select(UnderwritingThread.thread_id).where(
                UnderwritingThread.underwriting_id == underwriting_id,
                UnderwritingThread.kind == kind,
            )
        )

    async def get_thread_ids(
        self, underwriting_ids: Collection[int], kind: str
    ) -> dict[int, int]:
        """``underwriting_id -> thread_id`` for those that have a thread."""
        if not underwriting_ids:
            return {}
        result = await self.db.execute(
            select(
                UnderwritingThread.underwriting_id, UnderwritingThread.thread_id
            ).where(
                UnderwritingThread.underwriting_id.in_(set(underwriting_ids)),
                UnderwritingThread.kind == kind,
            )
        )
        return {
            underwriting_id: thread_id for underwriting_id, thread_id in result.all()
        }

    async def insert_link(
        self, underwriting_id: int, kind: str, thread_id: int
    ) -> int | None:
        """Link a thread unless one already exists for ``(underwriting_id, kind)``.

        Returns ``thread_id`` if this call created the link, ``None`` if another
        transaction got there first. If that transaction has not committed yet,
        Postgres waits for it, then reports the conflict (or inserts, if it
        rolled back).
        """
        return await self.db.scalar(
            insert(UnderwritingThread)
            .values(underwriting_id=underwriting_id, kind=kind, thread_id=thread_id)
            .on_conflict_do_nothing(index_elements=["underwriting_id", "kind"])
            .returning(UnderwritingThread.thread_id)
        )
