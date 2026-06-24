from app.iron_bank.defaults import UW_CONFIG_DEFAULTS
from app.iron_bank.schemas.uw_config import UwConfigSchema


def test_uw_config_schema_includes_annual_re_appreciation_pct():
    config = UwConfigSchema.model_validate(
        {
            "interest_rate": 0.0688,
            "loan_term_years": 30,
            "down_payment": 0.1,
            "closing_costs": 0.03,
            "fred": {"value": 0.065, "date": "2024-06-01"},
            "land_assumptions": 0.2,
            "annual_re_appreciation_pct": 0.04,
            "tax_rate": 0.37,
            "co_hosting_pct": 0,
        }
    )

    assert config.annual_re_appreciation_pct == 0.04
    assert config.co_hosting_pct == 0
    assert "co_hosting" not in config.model_dump()


def test_uw_config_defaults_include_annual_re_appreciation_pct():
    assert UW_CONFIG_DEFAULTS.annual_re_appreciation_pct == 0.04


def test_uw_config_defaults_use_singular_co_hosting_pct():
    assert UW_CONFIG_DEFAULTS.co_hosting_pct == 0
    assert "co_hosting" not in UW_CONFIG_DEFAULTS.model_dump()
