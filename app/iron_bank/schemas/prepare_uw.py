from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.iron_bank.schemas.get_underwriting import (
    ConstructionAmenityOption,
    ConstructionRemodelingOption,
    ZillowProperty,
)
from app.iron_bank.schemas.uw_config import UwConfigSchema


class PreparedOpexCleaning(BaseModel):
    fee: Decimal | None = None
    num_of_turns: Decimal | None = None


class PreparedOpexRange(BaseModel):
    low: Decimal | None = None
    high: Decimal | None = None


class PreparedOpexRanged(BaseModel):
    pool_hot_tub: PreparedOpexRange = Field(default_factory=PreparedOpexRange)


class PreparedOpex(BaseModel):
    cleaning: PreparedOpexCleaning = Field(default_factory=PreparedOpexCleaning)
    ranged: PreparedOpexRanged = Field(default_factory=PreparedOpexRanged)
    absolute: dict[str, Any] = Field(default_factory=dict)
    # Annual property tax rate as a fraction of purchase price. Kept raw here;
    # the payload builder applies purchase price to derive the monthly amount.
    property_tax_pct: Decimal | None = None


class MarketContext(BaseModel):
    """Everything a draft underwriting derives from its market, minus the property.

    Split out of ``PrepareUwDataResult`` so both entry points can share it: the
    automated flow keys it off the scheduled listing's preset market, while the
    non-automated create-from-URL flow gets it from the caller's ``market_id``
    (or a zeroed template when there is none). Carries no property data, so it
    is independent of where the listing came from.
    """

    market_name: str | None = None
    market_id: int | None = None
    market_slug: str | None = None
    analyst_owner_id: int | None = None
    opex: PreparedOpex
    construction_amenities: list[ConstructionAmenityOption]
    construction_remodeling: list[ConstructionRemodelingOption]
    # ids into construction_amenities that this market requires on every deal
    # (market_keys_master.must_have_amenities). The payload builder seeds one
    # optimization item per id.
    must_have_amenity_ids: list[int] = Field(default_factory=list)
    config: UwConfigSchema


class BedroomContext(BaseModel):
    """The seed values that change when an analyst changes the bedroom count.

    Deliberately narrower than ``MarketContext``: it carries *only* what is
    keyed on ``(market_id, bedrooms)``, so the FE has nothing it must remember
    to ignore. Excluded because none of it moves with bedrooms — the remodeling
    catalog, must-have amenities, the STR Cribs option (keyed on area), the
    sqft-keyed opex rows (internet / pest control / utilities), and every
    financing/FRED default.

    The FE merges these into the edit form and PUTs as usual; bedrooms itself
    has no formula, so the normal recalculation cascade does the rest.
    """

    bedrooms: int
    opex: PreparedOpex
    # Derived server-side rather than left to the FE so the persisted blobs stay
    # byte-identical to the ones creation produces (same shape, same
    # source/inputs provenance keys). Placed straight onto uw_details.
    cleaning_cost: dict[str, Any] | None = None
    property_taxes: dict[str, Any] | None = None
    # Only the two bedroom-keyed synthetic options: "Furniture / Decor /
    # Essentials" (id 0) and "Install / Staging / Warehousing" (id -1). All
    # three price tiers are returned so a re-tiered analyst choice is honoured
    # rather than forced back to Mid.
    furnishing_options: list[ConstructionAmenityOption] = Field(default_factory=list)
    land_assumptions_pct: Decimal | None = None
    annual_re_appreciation_pct: Decimal | None = None


class PrepareUwDataResult(MarketContext):
    zillow_property: ZillowProperty
    # Address parts kept alongside ``zillow_property`` rather than inside it:
    # they land on the underwritings row's own street/city/state columns, so
    # they're not part of the ZillowProperty response contract.
    street: str | None = None
    city: str | None = None
    state: str | None = None
