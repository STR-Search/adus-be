from typing import Literal
from pydantic import BaseModel


class FredRateSchema(BaseModel):
    value: float
    date: str


class CoHostingFeeSchema(BaseModel):
    fee: float
    fee_type: Literal["percent", "flat"]


class CoHostingSchema(BaseModel):
    self: CoHostingFeeSchema
    company: CoHostingFeeSchema
    va: CoHostingFeeSchema


class UwConfigSchema(BaseModel):
    interest_rate: float
    loan_term_years: int
    down_payment: float
    closing_costs: float
    fred: FredRateSchema
    land_assumptions: float
    tax_rate: float
    co_hosting: CoHostingSchema


class CommonExtrasSchema(BaseModel):
    blinds: float
    appliances: float
    landscaping: float
    washer_dryer: float
    baseboards_molding: float
