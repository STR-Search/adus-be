from app.iron_bank.controllers.deal_status_controller import DealStatusController
from app.iron_bank.enums import DealStatus
from app.iron_bank.services.deal_status_service import DealStatusService


def test_get_deal_statuses_returns_fe_options():
    result = DealStatusController(DealStatusService()).get_deal_statuses()

    assert result.statuses[0].model_dump() == {
        "key": "template_generated",
        "label": "Template_generated",
        "sort_order": 1,
    }


def test_get_allowed_transitions_returns_role_filtered_targets():
    result = DealStatusController(DealStatusService()).get_allowed_transitions(
        current_status=DealStatus.ANALYST_STARTED,
        actor_role="analyst",
    )

    assert [option.key for option in result.allowed_transitions] == [
        "analyst_completed",
        "maybe",
        "re_forecast_revenue",
    ]
