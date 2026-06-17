from app.iron_bank.schemas.uw_config import UwConfigSchema

UW_CONFIG_DEFAULTS = UwConfigSchema(
    interest_rate=0.0688,
    loan_term_years=30,
    down_payment=0.1,
    closing_costs=0.03,
    fred={"value": 0.065, "date": "2024-06-01"},
    land_assumptions=0.2,
    annual_re_appreciation_pct=0.04,
    tax_rate=0.37,
    co_hosting_pct=0,
)
