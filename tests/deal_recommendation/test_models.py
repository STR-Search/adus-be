from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKeyConstraint

import app.deal_recommendation.models  # noqa: F401
from app.core.database import Base
from app.deal_recommendation.repositories.run_repository import RunUsage

TABLES = (
    "conversations",
    "messages",
    "agent_runs",
    "tool_calls",
    "client_profiles",
    "recommendations",
)


def _table(name):
    return Base.metadata.tables[f"deal_recommendation.{name}"]


def test_tables_live_in_deal_recommendation_schema():
    for name in TABLES:
        assert _table(name).schema == "deal_recommendation"


def test_message_role_check_is_user_or_assistant():
    checks = [c for c in _table("messages").constraints if isinstance(c, CheckConstraint)]
    text = " ".join(str(c.sqltext) for c in checks)
    assert "'user'" in text and "'assistant'" in text
    assert "'system'" not in text


def test_recommendations_has_no_fk_to_iron_bank():
    fks = [c for c in _table("recommendations").constraints if isinstance(c, ForeignKeyConstraint)]
    targets = {fk.referred_table.fullname for fk in fks}
    assert not any(t.startswith("iron_bank.") for t in targets)


def test_run_usage_cost():
    usage = RunUsage(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_tokens=2_000_000,
        cache_write_tokens=0,
    )
    assert usage.cost_usd() == Decimal("3.4000")


def test_run_usage_cost_includes_cache_writes():
    assert RunUsage(cache_write_tokens=1_000_000).cost_usd() == Decimal("2.5000")
