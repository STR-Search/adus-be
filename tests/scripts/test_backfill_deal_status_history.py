from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.iron_bank.models import Underwriting
from scripts.backfill_deal_status_history import (
    SEED_NOTE,
    head_seed_for,
    target_label,
)

APPROVED = datetime(2025, 3, 14, tzinfo=UTC)
UPDATED = datetime(2026, 9, 1, tzinfo=UTC)
CREATED = datetime(2025, 1, 2, tzinfo=UTC)


def _underwriting(**overrides):
    values = dict(
        id=12,
        deal_status="analyst_started",
        approver_id=7,
        deal_approved=APPROVED,
        updated_at=UPDATED,
        created_at=CREATED,
        purchase_price=Decimal("400000.00"),
    )
    values.update(overrides)
    return Underwriting(**values)


@pytest.mark.parametrize("status", ["present_to_clients", "client_under_contract"])
def test_approved_statuses_use_approval_date_and_approver(status):
    seed = head_seed_for(_underwriting(deal_status=status))
    assert seed.occurred_at == APPROVED
    assert seed.actor_user_id == 7


def test_approved_status_without_approval_date_falls_back_to_updated_at():
    seed = head_seed_for(
        _underwriting(deal_status="present_to_clients", deal_approved=None)
    )
    assert seed.occurred_at == UPDATED
    assert seed.actor_user_id == 7


def test_other_statuses_use_updated_at_and_no_actor():
    # deal_approved can be set on a deal later moved back to "maybe"; it says
    # nothing about when the deal entered its current status.
    seed = head_seed_for(_underwriting(deal_status="maybe"))
    assert seed.occurred_at == UPDATED
    assert seed.actor_user_id is None


def test_falls_back_to_created_at_then_none():
    assert head_seed_for(_underwriting(updated_at=None)).occurred_at == CREATED
    assert (
        head_seed_for(_underwriting(updated_at=None, created_at=None)).occurred_at
        is None
    )


def test_seed_is_a_backfill_head_with_full_snapshot():
    seed = head_seed_for(_underwriting())
    assert (seed.subject_type, seed.subject_id, seed.flow) == (
        "underwriting",
        12,
        "deal_status",
    )
    assert seed.to_status == "analyst_started"
    assert seed.source == "backfill"
    assert seed.note == SEED_NOTE
    assert seed.snapshot.payload["purchase_price"] == "400000.00"
    assert seed.snapshot.payload["deal_status"] == "analyst_started"


def test_target_label():
    assert target_label("postgresql+asyncpg://x@db.czixmnswofswzcuhgnwa.supabase.co") == "DEV"
    assert target_label("postgresql+asyncpg://x@db.cnunaeslrrgetewuxsty.supabase.co") == "PROD"
    assert target_label("postgresql+asyncpg://localhost/x") == "UNKNOWN"
