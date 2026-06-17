from typing import Any, Protocol

import structlog
from fastapi.encoders import jsonable_encoder

from app.airbnb_public.schemas.cleaned_data import RevenuePotentialPercentiles
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.save_underwriting import (
    ForecastedRevenueInput,
    SaveUnderwritingPayload,
    SaveUnderwritingResult,
)
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator
from app.markets.schemas.market import MarketKeysMasterSchema
from app.zillow.models.scheduled_listings import ScheduledListing

logger = structlog.get_logger(__name__)


class MarketReader(Protocol):
    async def get_by_id(self, market_id: int) -> MarketKeysMasterSchema | None: ...


class ListingReader(Protocol):
    async def get_by_zpid(self, zpid: str) -> ScheduledListing | None: ...


class CleanedDataRevenueReader(Protocol):
    async def get_revenue_potential_percentiles(
        self,
        *,
        key_market: str,
        bedrooms: int,
    ) -> RevenuePotentialPercentiles | None: ...


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
        market_service: MarketReader | None = None,
        listings_service: ListingReader | None = None,
        cleaned_data_service: CleanedDataRevenueReader | None = None,
    ):
        self.repository = repository
        self.calculator = calculator or UnderwritingCalculator()
        self.market_service = market_service
        self.listings_service = listings_service
        self.cleaned_data_service = cleaned_data_service

    async def save(self, payload: SaveUnderwritingPayload) -> SaveUnderwritingResult:
        data = payload.model_dump(exclude_unset=True)

        underwriting_data = {
            key: value for key, value in data.items() if key not in self._CHILD_FIELDS
        }
        tax_data = self._build_tax_data(payload)
        detail_data = await self._build_detail_data(payload, tax_data)
        self._apply_calculated_underwriting_fields(
            underwriting_data,
            detail_data,
            payload.optimization_list,
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

    async def _build_detail_data(
        self,
        payload: SaveUnderwritingPayload,
        tax_data: dict | None = None,
    ) -> dict | None:
        if payload.details is None:
            logger.debug("_build_detail_data: no details on payload, skipping")
            return None

        detail_data = self._without_empty_values(
            payload.details.model_dump(exclude_unset=True)
        )
        logger.debug(
            "_build_detail_data: detail fields present",
            fields=list(detail_data.keys()),
            has_purchase_details=payload.details.purchase_details is not None,
            has_forecasted_revenue=payload.details.forecasted_revenue is not None,
        )

        if payload.details.purchase_details is not None:
            detail_data["purchase_details"] = (
                self.calculator.calculate_purchase_details(
                    payload.details.purchase_details
                )
            )

        forecasted_revenue_input = payload.details.forecasted_revenue
        logger.debug(
            "_build_detail_data: forecasted revenue source",
            from_payload=forecasted_revenue_input is not None,
            will_auto_build=forecasted_revenue_input is None and "purchase_details" in detail_data,
        )
        if forecasted_revenue_input is None and "purchase_details" in detail_data:
            forecasted_revenue_input = await self._build_forecasted_revenue_input(
                payload
            )

        if forecasted_revenue_input is not None:
            if "purchase_details" not in detail_data:
                raise ValueError(
                    "purchase_details is required to calculate forecasted revenue"
                )
            detail_data["forecasted_revenue"] = (
                self.calculator.calculate_forecasted_revenue(
                    forecasted_revenue=forecasted_revenue_input,
                    purchase_details=detail_data["purchase_details"],
                    operating_expenses=payload.operating_expenses,
                    optimization_items=payload.optimization_list,
                )
            )

        will_calc_y1 = (
            "forecasted_revenue" in detail_data
            and tax_data is not None
            and "purchase_details" in detail_data
        )
        logger.debug(
            "_build_detail_data: y1 coc tax savings",
            will_calculate=will_calc_y1,
            has_tax_data=tax_data is not None,
        )
        if will_calc_y1:
            detail_data["y1_coc_incl_tax_savings"] = (
                self.calculator.calculate_y1_coc_incl_tax_savings(
                    forecasted_revenue=detail_data["forecasted_revenue"],
                    tax_data=tax_data,
                    purchase_details=detail_data["purchase_details"],
                    optimization_items=payload.optimization_list,
                )
            )

        return detail_data

    async def _build_forecasted_revenue_input(
        self,
        payload: SaveUnderwritingPayload,
    ) -> ForecastedRevenueInput | None:
        if (
            self.market_service is None
            or self.listings_service is None
            or self.cleaned_data_service is None
        ):
            logger.debug(
                "_build_forecasted_revenue_input: skipping — one or more services not configured",
                has_market_service=self.market_service is not None,
                has_listings_service=self.listings_service is not None,
                has_cleaned_data_service=self.cleaned_data_service is not None,
            )
            return None

        if payload.market_id is None:
            raise ValueError(
                "market_id is required to calculate forecasted revenue from Airbnb data"
            )
        if payload.zpid is None:
            raise ValueError(
                "zpid is required to calculate forecasted revenue from Airbnb data"
            )

        market = await self.market_service.get_by_id(payload.market_id)
        logger.debug(
            "_build_forecasted_revenue_input: market lookup",
            market_id=payload.market_id,
            market_name_current=market.market_name_current if market else None,
        )
        if market is None or market.market_name_current is None:
            raise ValueError(
                "market_name_current is required for Airbnb revenue lookup"
            )

        listing = await self.listings_service.get_by_zpid(payload.zpid)
        logger.debug(
            "_build_forecasted_revenue_input: listing lookup",
            zpid=payload.zpid,
            beds=listing.beds if listing else None,
        )
        if listing is None or listing.beds is None:
            raise ValueError("listing beds are required for Airbnb revenue lookup")

        percentiles = await self.cleaned_data_service.get_revenue_potential_percentiles(
            key_market=market.market_name_current,
            bedrooms=listing.beds,
        )
        logger.debug(
            "_build_forecasted_revenue_input: percentiles lookup",
            key_market=market.market_name_current,
            bedrooms=listing.beds,
            percentiles_low=percentiles.low if percentiles else None,
            percentiles_mid=percentiles.mid if percentiles else None,
            percentiles_high=percentiles.high if percentiles else None,
        )
        if percentiles is None:
            raise ValueError(
                "Airbnb revenue percentiles were not found for the market and bedrooms"
            )

        forecasted_revenue_input = ForecastedRevenueInput.model_validate(
            {
                "co_hosting_fee_pct": 0,
                "annual_re_appreciation_pct": 0.0425,
                "scenarios": {
                    "low": {"forecasted_revenue": percentiles.low},
                    "mid": {"forecasted_revenue": percentiles.mid},
                    "high": {"forecasted_revenue": percentiles.high},
                },
            }
        )
        logger.debug(
            "_build_forecasted_revenue_input: estimated forecasted revenue",
            co_hosting_fee_pct=forecasted_revenue_input.co_hosting_fee_pct,
            annual_re_appreciation_pct=forecasted_revenue_input.annual_re_appreciation_pct,
            low_forecasted_revenue=forecasted_revenue_input.scenarios.low.forecasted_revenue,
            mid_forecasted_revenue=forecasted_revenue_input.scenarios.mid.forecasted_revenue,
            high_forecasted_revenue=forecasted_revenue_input.scenarios.high.forecasted_revenue,
        )
        return forecasted_revenue_input

    def _apply_calculated_underwriting_fields(
        self,
        underwriting_data: dict[str, Any],
        detail_data: dict | None,
        optimization_items: list,
    ) -> None:
        if detail_data is None:
            return

        purchase_details = detail_data.get("purchase_details")
        if purchase_details is not None:
            underwriting_data["purchase_price"] = purchase_details["purchase_price"]

        forecasted_revenue = detail_data.get("forecasted_revenue")
        if forecasted_revenue is not None:
            scenarios = forecasted_revenue["scenarios"]
            underwriting_data["low_gross_revenue"] = scenarios["low"][
                "forecasted_revenue"
            ]
            underwriting_data["mid_gross_revenue"] = scenarios["mid"][
                "forecasted_revenue"
            ]
            underwriting_data["high_gross_revenue"] = scenarios["high"][
                "forecasted_revenue"
            ]

            if purchase_details is not None:
                total_oop = self.calculator.calculate_total_oop(
                    purchase_details=purchase_details,
                    optimization_items=optimization_items,
                )
                cash_on_cash = self.calculator.calculate_cash_on_cash(
                    forecasted_revenue=forecasted_revenue,
                    total_oop=total_oop,
                )
                underwriting_data["total_oop"] = total_oop
                underwriting_data["prr"] = self.calculator.calculate_prr(
                    purchase_price=purchase_details["purchase_price"],
                    mid_gross_revenue=scenarios["mid"]["forecasted_revenue"],
                )
                underwriting_data["budget_to_pp"] = (
                    self.calculator.calculate_budget_to_pp(
                        total_oop=total_oop,
                        purchase_price=purchase_details["purchase_price"],
                    )
                )
                underwriting_data["l_cash_on_cash"] = cash_on_cash["low_pct"]
                underwriting_data["m_cash_on_cash"] = cash_on_cash["mid_pct"]
                underwriting_data["h_cash_on_cash"] = cash_on_cash["high_pct"]

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
