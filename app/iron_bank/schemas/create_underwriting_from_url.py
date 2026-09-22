from pydantic import BaseModel, Field, field_validator

from app.iron_bank.schemas.market_selection import normalize_absent_market


class CreateUnderwritingFromUrlPayload(BaseModel):
    url: str = Field(..., description="Zillow property (homedetails) URL")
    market_id: int | None = Field(
        None,
        description=(
            "Market to seed operating expenses and rehab line items from. "
            "Omit (or send 0) for a market-less deal: the rows are still seeded "
            "so the analyst has the full template, but every amount comes "
            "through as 0."
        ),
    )

    @field_validator("market_id")
    @classmethod
    def _normalize_absent_market(cls, value: int | None) -> int | None:
        return normalize_absent_market(value)
