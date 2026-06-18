from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.deal_status import (
    DealStatusOptionsResult,
    DealStatusTransitionsResult,
)
from app.iron_bank.services.deal_status_service import DealStatusService


class DealStatusController:
    def __init__(self, service: DealStatusService):
        self.service = service

    def get_deal_statuses(self) -> DealStatusOptionsResult:
        return self.service.list_status_options()

    def get_allowed_transitions(
        self,
        *,
        current_status: DealStatus,
        actor_role: str,
    ) -> DealStatusTransitionsResult:
        return self.service.get_allowed_transitions(
            current_status=current_status,
            actor_role=actor_role,
        )
