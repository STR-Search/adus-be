from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.batch_prepare_uw import BatchPrepareUwByMarketResult
from app.workflows.batch_prepare_and_save_underwritings_by_market_job import (
    BatchPrepareAndSaveUnderwritingsByMarketJob,
)


class WorkflowTriggerController:
    """Exposes workflow jobs as HTTP-triggerable endpoints."""

    def __init__(
        self,
        batch_prepare_by_market_job: BatchPrepareAndSaveUnderwritingsByMarketJob,
    ):
        self.batch_prepare_by_market_job = batch_prepare_by_market_job

    async def batch_prepare_by_market(
        self,
        *,
        market_id: int,
        since_hours: int,
        limit: int | None = None,
    ) -> BatchPrepareUwByMarketResult:
        try:
            result = await self.batch_prepare_by_market_job.run(
                market_id=market_id,
                since_hours=since_hours,
                limit=limit,
            )
            return BatchPrepareUwByMarketResult.model_validate(result)
        except Exception as e:
            logger.error(
                "iron_bank.workflow_trigger.batch_prepare_by_market.error",
                market_id=market_id,
                since_hours=since_hours,
                limit=limit,
                error=str(e),
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to prepare and save underwritings for market",
            )
