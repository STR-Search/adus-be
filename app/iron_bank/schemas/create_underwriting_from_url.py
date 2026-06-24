from pydantic import BaseModel, Field


class CreateUnderwritingFromUrlPayload(BaseModel):
    url: str = Field(..., description="Zillow property (homedetails) URL")
