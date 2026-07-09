from app.iron_bank.enums import DealStatus
from app.iron_bank.schemas.deal_status import (
    DealStatusOption,
    DealStatusOptionsResult,
    DealStatusTransitionsResult,
)


class DealStatusTransitionError(ValueError):
    pass


STATUS_OPTIONS: tuple[tuple[DealStatus, str, int], ...] = (
    (DealStatus.TEMPLATE_GENERATED, "Template Generated", 1),
    (DealStatus.ANALYST_STARTED, "Analyst Started", 2),
    (DealStatus.ANALYST_COMPLETED, "Analyst Completed", 3),
    (DealStatus.DELETE_ZILLOW, "Delete - Zillow", 4),
    (DealStatus.DELETE_DEAL, "Delete - Deal", 5),
    (DealStatus.MAYBE, "Maybe", 6),
    (DealStatus.RE_FORECAST_REVENUE, "Re-Forecast Revenue", 7),
    (DealStatus.AWAITING_REALTOR_DETAILS, "Awaiting Realtor Details", 8),
    (DealStatus.PRESENT_TO_CLIENTS, "Present To Clients", 9),
    (DealStatus.CLIENT_UNDER_CONTRACT, "Client Under Contract", 10),
    (DealStatus.TRAINING_DEAL, "Training Deal", 11),
    (DealStatus.PREVIOUSLY_UNDERWRITTEN_NO_STATUS, "Previously Underwritten - No Status", 12),
)

DEAL_STATUS_TRANSITIONS: dict[DealStatus, set[DealStatus]] = {
    DealStatus.TEMPLATE_GENERATED: {
        DealStatus.ANALYST_STARTED,
        DealStatus.TRAINING_DEAL,
        DealStatus.DELETE_ZILLOW,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.ANALYST_STARTED: {
        DealStatus.ANALYST_COMPLETED,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_ZILLOW,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.ANALYST_COMPLETED: {
        DealStatus.AWAITING_REALTOR_DETAILS,
        DealStatus.PRESENT_TO_CLIENTS,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.AWAITING_REALTOR_DETAILS: {
        DealStatus.PRESENT_TO_CLIENTS,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.MAYBE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.PRESENT_TO_CLIENTS: {
        DealStatus.CLIENT_UNDER_CONTRACT,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.MAYBE: {
        DealStatus.ANALYST_STARTED,
        DealStatus.RE_FORECAST_REVENUE,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.RE_FORECAST_REVENUE: {
        DealStatus.ANALYST_STARTED,
        DealStatus.ANALYST_COMPLETED,
        DealStatus.DELETE_DEAL,
    },
    DealStatus.CLIENT_UNDER_CONTRACT: set(),
    DealStatus.TRAINING_DEAL: set(),
    DealStatus.DELETE_ZILLOW: set(),
    DealStatus.DELETE_DEAL: set(),
    DealStatus.PREVIOUSLY_UNDERWRITTEN_NO_STATUS: set(),
}

ROLE_ALLOWED_TARGETS: dict[str, set[DealStatus]] = {
    "analyst": {
        DealStatus.ANALYST_STARTED,
        DealStatus.ANALYST_COMPLETED,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
    },
    "approver": {
        DealStatus.AWAITING_REALTOR_DETAILS,
        DealStatus.PRESENT_TO_CLIENTS,
        DealStatus.CLIENT_UNDER_CONTRACT,
        DealStatus.MAYBE,
        DealStatus.RE_FORECAST_REVENUE,
    },
    "admin": set(DealStatus),
}


class DealStatusService:
    def list_status_options(self) -> DealStatusOptionsResult:
        return DealStatusOptionsResult(
            statuses=[self._to_option(status) for status, _, _ in STATUS_OPTIONS]
        )

    def get_allowed_transitions(
        self,
        *,
        current_status: DealStatus,
        actor_role: str,
    ) -> DealStatusTransitionsResult:
        valid_targets = DEAL_STATUS_TRANSITIONS[current_status]
        role_targets = ROLE_ALLOWED_TARGETS.get(actor_role, set())
        allowed = valid_targets & role_targets

        return DealStatusTransitionsResult(
            current_status=current_status.value,
            actor_role=actor_role,
            allowed_transitions=[
                self._to_option(status)
                for status, _, _ in STATUS_OPTIONS
                if status in allowed
            ],
        )

    def validate_transition(
        self,
        *,
        current_status: DealStatus,
        next_status: DealStatus,
        actor_role: str,
    ) -> None:
        allowed = {
            option.key
            for option in self.get_allowed_transitions(
                current_status=current_status,
                actor_role=actor_role,
            ).allowed_transitions
        }
        if next_status.value not in allowed:
            raise DealStatusTransitionError(
                f"{actor_role} cannot transition deal_status from "
                f"{current_status.value} to {next_status.value}"
            )

    def _to_option(self, status: DealStatus) -> DealStatusOption:
        for candidate, label, sort_order in STATUS_OPTIONS:
            if candidate == status:
                return DealStatusOption(
                    key=status.value,
                    label=label,
                    sort_order=sort_order,
                )
        raise ValueError(f"Unknown deal status: {status}")
