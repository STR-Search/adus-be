from app.iron_bank.schemas.uw_config import CommonExtrasSchema, UwConfigSchema

UW_CONFIG_DEFAULTS = UwConfigSchema(
    interest_rate=0.07,
    loan_term_years=30,
    down_payment=0.1,
    closing_costs=0.03,
    fred={"value": 0.065, "date": "2024-06-01"},
    land_assumptions=0.2,
    tax_rate=0.37,
    co_hosting={
        "self": {"fee": 0.0, "fee_type": "percent"},
        "company": {"fee": 0.2, "fee_type": "percent"},
        "va": {"fee": 12000, "fee_type": "flat"},
    },
)

COMMON_EXTRAS_DEFAULTS = CommonExtrasSchema(
    blinds=1500,
    appliances=5000,
    landscaping=5000,
    washer_dryer=2000,
    baseboards_molding=2500,
)
