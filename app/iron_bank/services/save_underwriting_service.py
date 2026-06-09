from typing import Any

from fastapi.encoders import jsonable_encoder

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.save_underwriting import (
    SaveUnderwritingPayload,
    SaveUnderwritingResult,
)


class SaveUnderwritingService:
    _CHILD_FIELDS = {
        "uw_details",
        "taxes",
        "optimization_list",
        "operating_expenses",
        "comp_set",
    }

    def __init__(self, repository: UnderwritingRepository):
        self.repository = repository

    async def save(self, payload: SaveUnderwritingPayload) -> SaveUnderwritingResult:
        data = payload.model_dump(exclude_unset=True)

        underwriting_data = {
            key: value for key, value in data.items() if key not in self._CHILD_FIELDS
        }
        detail_data = (
            self._without_empty_values(
                payload.uw_details.model_dump(exclude_unset=True)
            )
            if payload.uw_details is not None
            else None
        )
        tax_data = (
            payload.taxes.model_dump(exclude_unset=True)
            if payload.taxes is not None
            else None
        )

        underwriting = await self.repository.create(
            underwriting_data=underwriting_data,
            detail_data=jsonable_encoder(detail_data) if detail_data else None,
            tax_data=tax_data,
            optimization_items=[
                item.model_dump(exclude_unset=True)
                for item in payload.optimization_list
            ],
            operating_expenses=[
                item.model_dump(exclude_unset=True)
                for item in payload.operating_expenses
            ],
            comp_set=[item.model_dump(exclude_unset=True) for item in payload.comp_set],
        )
        return SaveUnderwritingResult(underwriting_id=underwriting.id)

    def _without_empty_values(self, data: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in data.items() if value is not None}
