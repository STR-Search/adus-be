import json
import uuid
from typing import Any

from app.core.database import AsyncSessionLocal
from app.core.logger import logger
from app.iron_bank.repositories.job_repository import JobRepository
from app.workflows.batch_prepare_and_save_underwritings_job import (
    BatchPrepareAndSaveUnderwritingsJob,
)
from app.workflows.batch_prepare_and_save_underwritings_by_market_job import (
    BatchPrepareAndSaveUnderwritingsByMarketJob,
)
from app.workflows.batch_prepare_and_save_underwritings_by_preset_job import (
    BatchPrepareAndSaveUnderwritingsByPresetJob,
)

# Job type discriminators — also stored on the jobs row.
JOB_TYPE_BATCH_ALL = "batch_prepare_all"
JOB_TYPE_BATCH_BY_MARKET = "batch_prepare_by_market"
JOB_TYPE_BATCH_BY_PRESET = "batch_prepare_by_preset"


def _json_safe(value: Any) -> Any:
    """Coerce a result dict to JSON-serializable form (UUID/Decimal -> str)."""
    return json.loads(json.dumps(value, default=str))


async def _dispatch(job_type: str, params: dict, db) -> dict:
    if job_type == JOB_TYPE_BATCH_ALL:
        job = BatchPrepareAndSaveUnderwritingsJob.from_session(db)
        return await job.run(
            since_hours=params["since_hours"],
            limit=params.get("limit"),
        )
    if job_type == JOB_TYPE_BATCH_BY_MARKET:
        job = BatchPrepareAndSaveUnderwritingsByMarketJob.from_session(db)
        return await job.run(
            market_id=params["market_id"],
            since_hours=params["since_hours"],
            limit=params.get("limit"),
        )
    if job_type == JOB_TYPE_BATCH_BY_PRESET:
        job = BatchPrepareAndSaveUnderwritingsByPresetJob.from_session(db)
        return await job.run(
            preset_id=uuid.UUID(params["preset_id"]),
            since_hours=params["since_hours"],
            limit=params.get("limit"),
        )
    raise ValueError(f"Unknown job_type: {job_type}")


async def run_batch_job(job_id: uuid.UUID, job_type: str, params: dict) -> None:
    """Execute a batch job out-of-band and record its outcome on the jobs row.

    Runs in a FastAPI BackgroundTask after the request has returned, so it must
    open its own DB session — the request-scoped session is already closed.
    """
    async with AsyncSessionLocal() as db:
        repo = JobRepository(db)
        await repo.mark_running(job_id)
        try:
            result = await _dispatch(job_type, params, db)
            await repo.mark_succeeded(job_id, _json_safe(result))
        except Exception as exc:
            logger.exception(
                "iron_bank.job_runner.failed",
                job_id=str(job_id),
                job_type=job_type,
            )
            await repo.mark_failed(job_id, str(exc))
