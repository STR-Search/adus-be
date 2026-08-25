from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.core.serialization import PlainDecimal

from .common import BaseResponse


class OpexByBedroomsSchema(BaseResponse):
    id: int
    market_id: int | None = None
    market_slug: str | None = None
    bedrooms: int | None = None
    pool_hot_tub_low: PlainDecimal | None = None
    pool_hot_tub_high: PlainDecimal | None = None
    outdoor_landscaping: PlainDecimal | None = None
    software: PlainDecimal | None = None
    insurance_hoi: PlainDecimal | None = None
    supplies: PlainDecimal | None = None
    capex_reserve: PlainDecimal | None = None
    cleaning_fee: PlainDecimal | None = None
    num_of_turns: PlainDecimal | None = None
    property_taxes: PlainDecimal | None = None
    land_value: PlainDecimal | None = None
    appreciation: PlainDecimal | None = None
    hoa_fees: PlainDecimal | None = None
    furnishings_low: PlainDecimal | None = None
    furnishings_mid: PlainDecimal | None = None
    furnishings_high: PlainDecimal | None = None
    consolidated_shipping: PlainDecimal | None = None


class OpexByBedroomsCreateSchema(BaseModel):
    market_id: int | None = None
    market_slug: str | None = None
    bedrooms: int | None = None
    pool_hot_tub_low: Decimal | None = None
    pool_hot_tub_high: Decimal | None = None
    outdoor_landscaping: Decimal | None = None
    software: Decimal | None = None
    insurance_hoi: Decimal | None = None
    supplies: Decimal | None = None
    capex_reserve: Decimal | None = None
    cleaning_fee: Decimal | None = None
    num_of_turns: Decimal | None = None
    property_taxes: Decimal | None = None
    land_value: Decimal | None = None
    appreciation: Decimal | None = None
    hoa_fees: Decimal | None = None
    furnishings_low: Decimal | None = None
    furnishings_mid: Decimal | None = None
    furnishings_high: Decimal | None = None
    consolidated_shipping: Decimal | None = None

    @model_validator(mode="after")
    def check_market_fields(self):
        if self.market_id is not None and self.market_slug is not None:
            raise ValueError("Provide either market_id or market_slug, not both")
        return self


class OpexByBedroomsUpdateSchema(BaseModel):
    market_id: int | None = None
    market_slug: str | None = None
    bedrooms: int | None = None
    pool_hot_tub_low: Decimal | None = None
    pool_hot_tub_high: Decimal | None = None
    outdoor_landscaping: Decimal | None = None
    software: Decimal | None = None
    insurance_hoi: Decimal | None = None
    supplies: Decimal | None = None
    capex_reserve: Decimal | None = None
    cleaning_fee: Decimal | None = None
    num_of_turns: Decimal | None = None
    property_taxes: Decimal | None = None
    land_value: Decimal | None = None
    appreciation: Decimal | None = None
    hoa_fees: Decimal | None = None
    furnishings_low: Decimal | None = None
    furnishings_mid: Decimal | None = None
    furnishings_high: Decimal | None = None
    consolidated_shipping: Decimal | None = None

    @model_validator(mode="after")
    def check_market_fields(self):
        if self.market_id is not None and self.market_slug is not None:
            raise ValueError("Provide either market_id or market_slug, not both")
        return self


class OpexBySizeSchema(BaseResponse):
    id: int
    market_id: int | None = None
    market_slug: str | None = None
    sqft: int | None = None
    internet: PlainDecimal | None = None
    pest_control: PlainDecimal | None = None
    utilities: PlainDecimal | None = None


class OpexBySizeCreateSchema(BaseModel):
    market_id: int | None = None
    market_slug: str | None = None
    sqft: int | None = None
    internet: Decimal | None = None
    pest_control: Decimal | None = None
    utilities: Decimal | None = None

    @model_validator(mode="after")
    def check_market_fields(self):
        if self.market_id is not None and self.market_slug is not None:
            raise ValueError("Provide either market_id or market_slug, not both")
        return self


class OpexBySizeUpdateSchema(BaseModel):
    market_id: int | None = None
    market_slug: str | None = None
    sqft: int | None = None
    internet: Decimal | None = None
    pest_control: Decimal | None = None
    utilities: Decimal | None = None

    @model_validator(mode="after")
    def check_market_fields(self):
        if self.market_id is not None and self.market_slug is not None:
            raise ValueError("Provide either market_id or market_slug, not both")
        return self
