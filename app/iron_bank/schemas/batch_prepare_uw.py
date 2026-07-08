import uuid
from typing import Any

from pydantic import BaseModel, Field


class BatchPrepareUwByMarketResult(BaseModel):
    market_id: int
    found: int
    processed: int
    saved: int
    skipped_existing: int
    skipped_no_purchase_price: int
    failed: int
    results: list[dict[str, Any]] = Field(default_factory=list)


class BatchPrepareUwByPresetResult(BaseModel):
    preset_id: uuid.UUID
    found: int
    processed: int
    saved: int
    skipped_existing: int
    skipped_no_purchase_price: int
    failed: int
    results: list[dict[str, Any]] = Field(default_factory=list)
