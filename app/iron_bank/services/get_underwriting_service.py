from decimal import Decimal
from typing import Any

from app.core.logger import logger
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.get_underwriting import (
    ConstructionAmenityOption,
    ConstructionRemodelingOption,
    EditContextData,
    EditContextualData,
    GetUnderwritingDetails,
    GetUnderwritingEditContextResult,
    GetUnderwritingResult,
    GetUnderwritingsResult,
    ZillowProperty,
)
from app.iron_bank.schemas.underwriting import UnderwritingRead
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService


class GetUnderwritingService:
    def __init__(
        self,
        repository: UnderwritingRepository,
        listings_service: Any = None,
        listing_details_service: Any = None,
        opex_by_bedrooms_service: Any = None,
        construction_amenities_service: Any = None,
        construction_remodeling_service: Any = None,
    ):
        self.repository = repository
        self.listings_service = listings_service
        self.listing_details_service = listing_details_service
        self.opex_by_bedrooms_service = opex_by_bedrooms_service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service

    async def get(self, underwriting_id: int) -> GetUnderwritingResult:
        underwriting = await self.repository.get_by_id(underwriting_id)
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")
        return self._to_result(underwriting)

    async def get_edit_context(
        self, underwriting_id: int
    ) -> GetUnderwritingEditContextResult:
        underwriting = await self.get(underwriting_id)

        # Automated underwritings point at a real scheduled_listings row, so
        # zillow data is hydrated live. Non-automated (manual POST) ones read
        # it back from the zillow_property persisted on uw_details.
        if underwriting.is_automated is True:
            zillow_property, opex_by_bedrooms = await self._zillow_from_listing(
                underwriting
            )
        else:
            zillow_property, opex_by_bedrooms = await self._zillow_from_stored(
                underwriting
            )

        # zillow_property is intrinsic property data, so it belongs on details
        # alongside purchase_details/forecasted_revenue — not in the contextual
        # bag, which holds only global edit-form reference data.
        self._apply_zillow_to_details(underwriting, zillow_property)

        amenities = await self.construction_amenities_service.get_all()
        remodeling = await self.construction_remodeling_service.get_all()
        amenity_options = PrepareUwDataService.build_amenities_options(
            opex_by_bedrooms, amenities
        )

        return GetUnderwritingEditContextResult(
            data=EditContextData(
                underwriting=underwriting,
                contextual=EditContextualData(
                    construction_amenities=[
                        ConstructionAmenityOption.model_validate(a)
                        for a in amenity_options
                    ],
                    construction_remodeling=[
                        ConstructionRemodelingOption.model_validate(r.model_dump())
                        for r in remodeling
                    ],
                ),
            )
        )

    @staticmethod
    def _apply_zillow_to_details(
        result: GetUnderwritingResult, zillow_property
    ) -> None:
        """Place a hydrated zillow_property onto the result's details.

        For non-automated underwritings the value is already present (read from
        storage); for automated ones this routes the live-hydrated value in.
        The value is coerced to the ``ZillowProperty`` schema so the response
        always follows the contract (extra fields dropped, types normalized),
        regardless of whether assignment validation is enabled.
        """
        if zillow_property is None:
            return
        coerced = ZillowProperty.model_validate(zillow_property)
        if result.details is None:
            result.details = GetUnderwritingDetails(zillow_property=coerced)
        else:
            result.details.zillow_property = coerced

    async def get_all(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        market_id: int | None = None,
        deal_status: str | None = None,
        analyst_id: int | None = None,
        min_purchase_price: Decimal | None = None,
        max_purchase_price: Decimal | None = None,
        min_total_oop: Decimal | None = None,
        max_total_oop: Decimal | None = None,
    ) -> GetUnderwritingsResult:
        items, total, pages = await self.repository.get_all_paginated(
            page=page,
            page_size=page_size,
            zpid=zpid,
            market_id=market_id,
            deal_status=deal_status,
            analyst_id=analyst_id,
            min_purchase_price=min_purchase_price,
            max_purchase_price=max_purchase_price,
            min_total_oop=min_total_oop,
            max_total_oop=max_total_oop,
        )
        results = [self._to_result(underwriting) for underwriting in items]
        await self._hydrate_automated_zillow(items, results)
        return GetUnderwritingsResult(
            data=results,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def _hydrate_automated_zillow(self, items, results) -> None:
        """Batch-hydrate zillow_property for automated underwritings in a list.

        Non-automated items already carry their stored zillow_property;
        automated ones persist nothing, so we fetch their listings live in two
        batched queries (one per zpid set) and route the transformed value onto
        each result's details — keeping zillow_property present across the list
        without an N+1 of per-item lookups.
        """
        if self.listings_service is None or self.listing_details_service is None:
            return

        automated = [
            (underwriting, result)
            for underwriting, result in zip(items, results)
            if underwriting.is_automated and underwriting.zpid
        ]
        if not automated:
            return

        zpids = [underwriting.zpid for underwriting, _ in automated]
        listings = await self.listings_service.get_by_zpids(zpids)
        listing_details = await self.listing_details_service.get_by_zpids(zpids)
        transformer = PrepareUwDataService()

        for underwriting, result in automated:
            listing = listings.get(underwriting.zpid)
            if listing is None:
                logger.warning(
                    "iron_bank.get_underwritings.listing_not_found",
                    underwriting_id=underwriting.id,
                    zpid=underwriting.zpid,
                    detail="no listing found for zpid — zillow_property will be unavailable",
                )
                continue
            zillow_property = transformer._transform_zillow_property(
                listing, listing_details.get(underwriting.zpid)
            )
            self._apply_zillow_to_details(result, zillow_property)

    def _to_result(self, underwriting) -> GetUnderwritingResult:
        return GetUnderwritingResult.model_validate(
            {
                **self._parent_data(underwriting),
                "details": self._detail_data(underwriting.detail),
                "taxes": self._tax_data(underwriting.taxes),
                "optimization_list": [
                    self._optimization_item_data(item)
                    for item in underwriting.optimization_items
                ],
                "operating_expenses": [
                    self._operating_expense_data(expense)
                    for expense in underwriting.operating_expenses
                ],
                "comp_set": [
                    self._comp_set_data(comp) for comp in underwriting.comp_set
                ],
            }
        )

    def _parent_data(self, underwriting) -> dict[str, Any]:
        # UnderwritingRead.model_fields covers UnderwritingBase plus id and the
        # column_property totals (optimization_total, operating_expense_total).
        # deal_status_label is a computed_field, so it's derived, not copied here.
        return {
            field: getattr(underwriting, field, None)
            for field in UnderwritingRead.model_fields
        }

    def _detail_data(self, detail) -> dict[str, Any] | None:
        if detail is None:
            return None
        return {
            "purchase_details": detail.purchase_details,
            "y1_coc_incl_tax_savings": detail.y1_coc_incl_tax_savings,
            "forecasted_revenue": detail.forecasted_revenue,
            "cleaning_cost": detail.cleaning_cost,
            "zillow_property": detail.zillow_property,
            "analyst_notes": detail.analyst_notes,
        }

    def _tax_data(self, taxes) -> dict[str, Any] | None:
        if taxes is None:
            return None
        return {
            "land_assumptions_pct": taxes.land_assumptions_pct,
            "sla_multiplier_pct": taxes.sla_multiplier_pct,
            "improvement_basis": taxes.improvement_basis,
            "estimated_short_life_assets": taxes.estimated_short_life_assets,
            "bonus_amount_pct": taxes.bonus_amount_pct,
            "tax_rate_pct": taxes.tax_rate_pct,
            "y1_loss_from_depreciation": taxes.y1_loss_from_depreciation,
            "tax_savings": taxes.tax_savings,
        }

    def _optimization_item_data(self, item) -> dict[str, Any]:
        return {
            "category": item.category,
            "total_price": item.total_price,
            "metric": item.metric,
            "base_price": item.base_price,
            "spec": item.spec,
            "tier": item.tier,
            "notes": item.notes,
        }

    def _operating_expense_data(self, expense) -> dict[str, Any]:
        return {
            "expense_name": expense.expense_name,
            "monthly_amount": expense.monthly_amount,
        }

    def _comp_set_data(self, comp) -> dict[str, Any]:
        return {
            "listing_url": comp.listing_url,
            "revenue": comp.revenue,
            "bedrooms": comp.bedrooms,
            "sleeps": comp.sleeps,
        }

    async def _zillow_from_listing(self, underwriting) -> tuple[Any, Any]:
        """Automated path: hydrate zillow data live from scheduled_listings."""
        if not underwriting.zpid:
            logger.warning(
                "iron_bank.get_underwriting.no_zpid",
                underwriting_id=underwriting.id,
                detail="underwriting has no zpid — furnishings prices will be unavailable",
            )
            return None, None
        if not underwriting.market_id:
            logger.warning(
                "iron_bank.get_underwriting.no_market_id",
                underwriting_id=underwriting.id,
                zpid=underwriting.zpid,
                detail="underwriting has no market_id — furnishings prices will be unavailable",
            )
            return None, None

        listing = await self.listings_service.get_by_zpid(underwriting.zpid)
        if listing is None:
            logger.warning(
                "iron_bank.get_underwriting.listing_not_found",
                underwriting_id=underwriting.id,
                zpid=underwriting.zpid,
                detail="no listing found for zpid — furnishings prices will be unavailable",
            )
            return None, None

        listing_details = await self.listing_details_service.get_by_zpid(
            underwriting.zpid
        )
        zillow_property = PrepareUwDataService()._transform_zillow_property(
            listing, listing_details
        )
        opex_by_bedrooms = await self._opex_by_bedrooms(
            underwriting, bedrooms=listing.beds
        )
        return zillow_property, opex_by_bedrooms

    async def _zillow_from_stored(self, underwriting) -> tuple[Any, Any]:
        """Non-automated path: read zillow data persisted on uw_details."""
        zillow_property = (
            underwriting.details.zillow_property if underwriting.details else None
        )
        if zillow_property is None:
            logger.warning(
                "iron_bank.get_underwriting.no_stored_zillow_property",
                underwriting_id=underwriting.id,
                detail="non-automated underwriting has no stored zillow_property",
            )
            return None, None
        if not underwriting.market_id:
            logger.warning(
                "iron_bank.get_underwriting.no_market_id",
                underwriting_id=underwriting.id,
                detail="underwriting has no market_id — furnishings prices will be unavailable",
            )
            return zillow_property, None

        opex_by_bedrooms = await self._opex_by_bedrooms(
            underwriting, bedrooms=zillow_property.bedrooms
        )
        return zillow_property, opex_by_bedrooms

    async def _opex_by_bedrooms(self, underwriting, *, bedrooms):
        opex_by_bedrooms = (
            await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(
                bedrooms=bedrooms, market_id=underwriting.market_id
            )
        )
        if opex_by_bedrooms is None:
            logger.warning(
                "iron_bank.get_underwriting.no_opex",
                underwriting_id=underwriting.id,
                market_id=underwriting.market_id,
                bedrooms=bedrooms,
                detail="no opex row found for market/bedrooms — furnishings prices will be unavailable",
            )
        return opex_by_bedrooms
