import uuid

from fastapi import BackgroundTasks, HTTPException

from app.iron_bank.repositories.job_repository import JobRepository
from app.iron_bank.schemas.job import JobCreatedResponse, JobStatusResponse
from app.workflows.job_runner import (
    JOB_TYPE_BATCH_BY_MARKET,
    JOB_TYPE_BATCH_BY_PRESET,
    run_batch_job,
)


class WorkflowTriggerController:
    """Accepts batch workflow requests, persists them as jobs, runs them async."""

    def __init__(self, job_repository: JobRepository):
        self.job_repository = job_repository

    async def _enqueue(
        self,
        *,
        job_type: str,
        params: dict,
        background: BackgroundTasks,
    ) -> JobCreatedResponse:
        job = await self.job_repository.create(job_type=job_type, params=params)
        # Commit so the row is durable and visible before the task runs / caller polls.
        await self.job_repository.db.commit()
        background.add_task(run_batch_job, job.id, job_type, params)
        return JobCreatedResponse(id=job.id, status=job.status)

    async def batch_prepare_by_market(
        self,
        *,
        market_id: int,
        since_hours: int,
        limit: int | None,
        background: BackgroundTasks,
    ) -> JobCreatedResponse:
        return await self._enqueue(
            job_type=JOB_TYPE_BATCH_BY_MARKET,
            params={
                "market_id": market_id,
                "since_hours": since_hours,
                "limit": limit,
            },
            background=background,
        )

    async def batch_prepare_by_preset(
        self,
        *,
        preset_id: uuid.UUID,
        since_hours: int,
        limit: int | None,
        background: BackgroundTasks,
    ) -> JobCreatedResponse:
        return await self._enqueue(
            job_type=JOB_TYPE_BATCH_BY_PRESET,
            params={
                "preset_id": str(preset_id),
                "since_hours": since_hours,
                "limit": limit,
            },
            background=background,
        )

    async def get_job(self, job_id: uuid.UUID) -> JobStatusResponse:
        job = await self.job_repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobStatusResponse.model_validate(job)
