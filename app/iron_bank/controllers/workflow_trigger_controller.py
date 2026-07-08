import uuid

from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.batch_prepare_uw import (
    BatchPrepareUwByMarketResult,
    BatchPrepareUwByPresetResult,
)
from app.workflows.batch_prepare_and_save_underwritings_by_market_job import (
    BatchPrepareAndSaveUnderwritingsByMarketJob,
)
from app.workflows.batch_prepare_and_save_underwritings_by_preset_job import (
    BatchPrepareAndSaveUnderwritingsByPresetJob,
)


class WorkflowTriggerController:
    """Exposes workflow jobs as HTTP-triggerable endpoints."""

    def __init__(
        self,
        batch_prepare_by_market_job: BatchPrepareAndSaveUnderwritingsByMarketJob,
        batch_prepare_by_preset_job: BatchPrepareAndSaveUnderwritingsByPresetJob,
    ):
        self.batch_prepare_by_market_job = batch_prepare_by_market_job
        self.batch_prepare_by_preset_job = batch_prepare_by_preset_job

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

    async def batch_prepare_by_preset(
        self,
        *,
        preset_id: uuid.UUID,
        since_hours: int,
        limit: int | None = None,
    ) -> BatchPrepareUwByPresetResult:
        try:
            result = await self.batch_prepare_by_preset_job.run(
                preset_id=preset_id,
                since_hours=since_hours,
                limit=limit,
            )
            return BatchPrepareUwByPresetResult.model_validate(result)
        except Exception as e:
            logger.error(
                "iron_bank.workflow_trigger.batch_prepare_by_preset.error",
                preset_id=preset_id,
                since_hours=since_hours,
                limit=limit,
                error=str(e),
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to prepare and save underwritings for preset",
            )
