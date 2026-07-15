import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.iron_bank.models import Job


class JobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, job_type: str, params: dict) -> Job:
        job = Job(job_type=job_type, params=params, status="queued")
        self.db.add(job)
        await self.db.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> Job | None:
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def mark_running(self, job_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="running", started_at=func.now())
        )
        await self.db.commit()

    async def mark_succeeded(self, job_id: uuid.UUID, result: dict) -> None:
        await self.db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="succeeded", result=result, finished_at=func.now())
        )
        await self.db.commit()

    async def mark_failed(self, job_id: uuid.UUID, error: str) -> None:
        await self.db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="failed", error=error, finished_at=func.now())
        )
        await self.db.commit()
