from pydantic import BaseModel, Field, field_validator


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
    def normalize_absent_market(cls, value: int | None) -> int | None:
        """Treat ``0`` as "no market selected".

        Clients send 0 from an unselected dropdown. There is no market with
        id 0 (``market_keys_master`` starts at 1), so without this the value
        flows through as a real id: the context loads empty and the insert then
        violates the FK to markets.market_keys_master. Folding it to None picks
        up the existing market-less path in
        ``PrepareUwDataJob.build_market_context``, which seeds the full template
        with zeroed amounts.
        """
        return None if value == 0 else value
