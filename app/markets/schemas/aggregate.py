from pydantic import BaseModel, model_validator


class UnderwritingQuerySchema(BaseModel):
    bedrooms: int
    sqft: int
    market_id: int | None = None
    market_slug: str | None = None

    @model_validator(mode="after")
    def check_market_fields(self):
        if self.market_id is not None and self.market_slug is not None:
            raise ValueError("Provide either market_id or market_slug, not both")
        return self
