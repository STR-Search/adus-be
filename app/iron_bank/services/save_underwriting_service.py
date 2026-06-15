from typing import Any

from fastapi.encoders import jsonable_encoder

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.save_underwriting import (
    SaveUnderwritingPayload,
    SaveUnderwritingResult,
)
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator


class SaveUnderwritingService:
    _CHILD_FIELDS = {
        "details",
        "taxes",
        "optimization_list",
        "operating_expenses",
        "comp_set",
    }

    def __init__(
        self,
        repository: UnderwritingRepository,
        calculator: UnderwritingCalculator | None = None,
    ):
        self.repository = repository
        self.calculator = calculator or UnderwritingCalculator()

    async def save(self, payload: SaveUnderwritingPayload) -> SaveUnderwritingResult:
        data = payload.model_dump(exclude_unset=True)

        underwriting_data = {
            key: value for key, value in data.items() if key not in self._CHILD_FIELDS
        }
        tax_data = self._build_tax_data(payload)
        detail_data = self._build_detail_data(payload, tax_data)

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

    def _build_detail_data(
        self,
        payload: SaveUnderwritingPayload,
        tax_data: dict | None = None,
    ) -> dict | None:
        if payload.details is None:
            return None

        detail_data = self._without_empty_values(
            payload.details.model_dump(exclude_unset=True)
        )
        if payload.details.purchase_details is not None:
            detail_data["purchase_details"] = (
                self.calculator.calculate_purchase_details(
                    payload.details.purchase_details
                )
            )

        if payload.details.forecasted_revenue is not None:
            if "purchase_details" not in detail_data:
                raise ValueError(
                    "purchase_details is required to calculate forecasted revenue"
                )
            detail_data["forecasted_revenue"] = (
                self.calculator.calculate_forecasted_revenue(
                    forecasted_revenue=payload.details.forecasted_revenue,
                    purchase_details=detail_data["purchase_details"],
                    operating_expenses=payload.operating_expenses,
                    optimization_items=payload.optimization_list,
                )
            )

        if (
            "forecasted_revenue" in detail_data
            and tax_data is not None
            and "purchase_details" in detail_data
        ):
            detail_data["y1_coc_incl_tax_savings"] = (
                self.calculator.calculate_y1_coc_incl_tax_savings(
                    forecasted_revenue=detail_data["forecasted_revenue"],
                    tax_data=tax_data,
                    purchase_details=detail_data["purchase_details"],
                    optimization_items=payload.optimization_list,
                )
            )

        return detail_data

    def _build_tax_data(self, payload: SaveUnderwritingPayload) -> dict | None:
        if payload.taxes is None:
            return None

        purchase_price = self._get_purchase_price(payload)
        if purchase_price is None:
            raise ValueError(
                "purchase_price is required to calculate underwriting taxes"
            )

        return self.calculator.calculate_taxes(
            taxes=payload.taxes,
            purchase_price=purchase_price,
            optimization_items=payload.optimization_list,
        )

    def _get_purchase_price(self, payload: SaveUnderwritingPayload):
        if payload.details is not None and payload.details.purchase_details is not None:
            return payload.details.purchase_details.purchase_price
        return payload.purchase_price
