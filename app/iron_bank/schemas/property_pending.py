from pydantic import BaseModel, ConfigDict


class UpdatePropertyPendingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property_pending: bool


class UpdatePropertyPendingResult(BaseModel):
    underwriting_id: int
    property_pending: bool
