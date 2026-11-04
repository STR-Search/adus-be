from pydantic import BaseModel, ConfigDict


class UpdateOffMarketPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    off_market: bool


class UpdateOffMarketResult(BaseModel):
    underwriting_id: int
    off_market: bool
