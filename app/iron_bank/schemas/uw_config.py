from pydantic import BaseModel


class FredRateSchema(BaseModel):
    value: float
    date: str


class UwConfigSchema(BaseModel):
    interest_rate: float
    loan_term_years: int
    down_payment: float
    closing_costs: float
    fred: FredRateSchema
    land_assumptions: float
    annual_re_appreciation_pct: float
    tax_rate: float
    co_hosting_pct: float
