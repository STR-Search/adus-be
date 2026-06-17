import pytest

from app.iron_bank.enums import DealStatus
from app.iron_bank.services.deal_status_service import (
    DealStatusService,
    DealStatusTransitionError,
)


def test_list_status_options_returns_fe_labels_and_stable_keys():
    result = DealStatusService().list_status_options()

    assert result.statuses[0].model_dump() == {
        "key": "template_generated",
        "label": "Template_generated",
        "sort_order": 1,
    }


def test_allowed_transitions_filters_by_actor_role():
    result = DealStatusService().get_allowed_transitions(
        current_status=DealStatus.ANALYST_STARTED,
        actor_role="analyst",
    )

    assert [option.key for option in result.allowed_transitions] == [
        "analyst_completed",
        "maybe",
        "re_forecast_revenue",
    ]


def test_validate_transition_rejects_role_without_permission():
    service = DealStatusService()

    with pytest.raises(DealStatusTransitionError):
        service.validate_transition(
            current_status=DealStatus.ANALYST_STARTED,
            next_status=DealStatus.PRESENT_TO_CLIENTS,
            actor_role="analyst",
        )


def test_validate_transition_accepts_role_with_permission():
    DealStatusService().validate_transition(
        current_status=DealStatus.ANALYST_STARTED,
        next_status=DealStatus.ANALYST_COMPLETED,
        actor_role="analyst",
    )
