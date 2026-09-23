from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.iron_bank.schemas.market_selection import normalize_absent_market


class CreateBlankUnderwritingPayload(BaseModel):
    """The little an analyst can supply for an off-market deal with no listing.

    ``purchase_price`` is mandatory because it gates the entire financing and
    tax seed: ``_build_details`` only emits ``purchase_details`` when a price is
    present, and the taxes row is skipped under the same condition. Without one
    the market config and the live FRED rate are fetched and then discarded,
    leaving the frontend to invent its own defaults and the deal to stop
    tracking FRED silently.
    """

    model_config = ConfigDict(extra="forbid")

    purchase_price: Decimal = Field(..., gt=0)
    listing_url: str | None = Field(
        None,
        description=(
            "Where the deal was found, if anywhere — an agent's page, a "
            "Facebook post, a Redfin link. Not validated as a Zillow URL: an "
            "off-market deal is precisely one that has no Zillow listing. "
            "Lands on the listing_url column and is mirrored into "
            "details.zillow_property.url."
        ),
    )
    market_id: int | None = Field(
        None,
        description=(
            "Market to seed operating expenses and rehab line items from. "
            "Omit (or send 0) for a market-less deal: the rows are still seeded "
            "so the analyst has the full template, but every amount comes "
            "through as 0."
        ),
    )
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: Decimal | None = None

    @field_validator("market_id")
    @classmethod
    def _normalize_absent_market(cls, value: int | None) -> int | None:
        return normalize_absent_market(value)
