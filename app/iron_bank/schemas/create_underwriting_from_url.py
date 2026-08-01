from pydantic import BaseModel, Field


class CreateUnderwritingFromUrlPayload(BaseModel):
    url: str = Field(..., description="Zillow property (homedetails) URL")
    market_id: int | None = Field(
        None,
        description=(
            "Market to seed operating expenses and rehab line items from. "
            "Omit for a market-less deal: the rows are still seeded so the "
            "analyst has the full template, but every amount comes through as 0."
        ),
    )
