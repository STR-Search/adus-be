from fastapi.encoders import jsonable_encoder

from app.iron_bank.enums import DealStatus
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.deal_status import UpdateDealStatusResult
from app.iron_bank.schemas.update_underwriting import (
    UpdateUnderwritingPayload,
    UpdateUnderwritingResult,
)
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator


class UpdateUnderwritingService(SaveUnderwritingService):
    def __init__(
        self,
        repository: UnderwritingRepository,
        calculator: UnderwritingCalculator | None = None,
    ):
        super().__init__(repository=repository, calculator=calculator)

    async def update(
        self,
        underwriting_id: int,
        payload: UpdateUnderwritingPayload,
    ) -> UpdateUnderwritingResult:
        data = payload.model_dump(exclude_unset=True)

        underwriting_data = {
            key: value for key, value in data.items() if key not in self._CHILD_FIELDS
        }
        tax_data = self._build_tax_data(payload) if "taxes" in data else None
        detail_data = (
            await self._build_detail_data(payload, tax_data)
            if "details" in data
            else None
        )
        self._apply_calculated_underwriting_fields(
            underwriting_data,
            detail_data,
            payload.optimization_list,
        )

        underwriting = await self.repository.update(
            underwriting_id=underwriting_id,
            underwriting_data=underwriting_data,
            detail_data=jsonable_encoder(detail_data) if detail_data else None,
            tax_data=tax_data,
            optimization_items=(
                [
                    item.model_dump(exclude_unset=True)
                    for item in payload.optimization_list
                ]
                if "optimization_list" in data
                else None
            ),
            operating_expenses=(
                [
                    item.model_dump(exclude_unset=True)
                    for item in payload.operating_expenses
                ]
                if "operating_expenses" in data
                else None
            ),
            comp_set=(
                [item.model_dump(exclude_unset=True) for item in payload.comp_set]
                if "comp_set" in data
                else None
            ),
        )
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        return UpdateUnderwritingResult(underwriting_id=underwriting.id)

    async def update_deal_status(
        self,
        *,
        underwriting_id: int,
        deal_status: DealStatus,
    ) -> UpdateDealStatusResult:
        underwriting = await self.repository.update(
            underwriting_id=underwriting_id,
            underwriting_data={"deal_status": deal_status},
        )
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        return UpdateDealStatusResult(
            underwriting_id=underwriting.id,
            deal_status=underwriting.deal_status,
        )
