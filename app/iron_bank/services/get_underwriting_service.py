from datetime import date
from decimal import Decimal
from typing import Any

from app.core.logger import logger
from app.iron_bank.enums import SortOrder, UnderwritingSortBy
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
    OpexOption,
    UnderwritingRealtorDetail,
    UserRef,
    ZillowProperty,
)
from app.iron_bank.schemas.underwriting import UnderwritingRead
from app.iron_bank.services import opex_catalog
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService
from app.iron_bank.services.reference_label_resolver import apply_reference_labels


class GetUnderwritingService:
    def __init__(
        self,
        repository: UnderwritingRepository,
        listings_service: Any = None,
        listing_details_service: Any = None,
        opex_by_bedrooms_service: Any = None,
        opex_by_size_service: Any = None,
        construction_amenities_service: Any = None,
        construction_remodeling_service: Any = None,
        str_cribs_service: Any = None,
        reference_data_service: Any = None,
        user_repository: Any = None,
        market_repository: Any = None,
        realtor_repository: Any = None,
    ):
        self.repository = repository
        self.listings_service = listings_service
        self.listing_details_service = listing_details_service
        self.opex_by_bedrooms_service = opex_by_bedrooms_service
        self.opex_by_size_service = opex_by_size_service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service
        self.str_cribs_service = str_cribs_service
        self.reference_data_service = reference_data_service
        self.user_repository = user_repository
        self.market_repository = market_repository
        self.realtor_repository = realtor_repository

    async def get(self, underwriting_id: int) -> GetUnderwritingResult:
        underwriting = await self.repository.get_by_id(underwriting_id)
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")
        result = self._to_result(underwriting)
        await self._enrich([result])
        return result

    async def get_edit_context(
        self, underwriting_id: int
    ) -> GetUnderwritingEditContextResult:
        underwriting = await self.get(underwriting_id)

        # Automated underwritings point at a real scheduled_listings row, so
        # zillow data is hydrated live. Non-automated (manual POST) ones read
        # it back from the zillow_property persisted on uw_details.
        if underwriting.is_automated is True:
            zillow_property, zillow_bedrooms = await self._zillow_from_listing(
                underwriting
            )
        else:
            zillow_property, zillow_bedrooms = await self._zillow_from_stored(
                underwriting
            )

        # The opex lookup keys on the underwriting's own bedroom count, so it no
        # longer depends on which zillow branch ran — or on that branch
        # succeeding at all. ``zillow_bedrooms`` is a fallback for rows predating
        # the column; drop it once
        # ``scripts/backfill_underwriting_bedrooms.py`` has run everywhere.
        opex_by_bedrooms = await self._opex_by_bedrooms(
            underwriting,
            bedrooms=(
                underwriting.bedrooms if underwriting.bedrooms is not None
                else zillow_bedrooms
            ),
        )

        # zillow_property is intrinsic property data, so it belongs on details
        # alongside purchase_details/forecasted_revenue — not in the contextual
        # bag, which holds only global edit-form reference data.
        self._apply_zillow_to_details(underwriting, zillow_property)

        amenities = await self.construction_amenities_service.get_all()
        remodeling = await self.construction_remodeling_service.get_all()

        # iron_bank reference data (deal tag options), grouped by set_code. The
        # (domain="iron_bank") options were already fetched into the service's
        # per-request cache by _populate_reference_labels, so this is a cache
        # hit rather than a second query.
        deal_tag_options: dict = {}
        if self.reference_data_service is not None:
            reference_data = await self.reference_data_service.get_reference_data(
                domain="iron_bank"
            )
            deal_tag_options = reference_data.options

        # zillow_property was just coerced onto details, so its area is the
        # single source for the cribs fee tier (both automated and stored
        # paths funnel through it).
        area = (
            underwriting.details.zillow_property.area
            if underwriting.details and underwriting.details.zillow_property
            else None
        )
        str_cribs_fee = (
            await self.str_cribs_service.get_by_area(area)
            if self.str_cribs_service is not None and area is not None
            else None
        )
        amenity_options = PrepareUwDataService.build_amenities_options(
            opex_by_bedrooms, amenities, str_cribs_fee
        )

        # The market's opex truth table for this deal's bedrooms and sqft, so the
        # edit form can show what the market says alongside what the analyst has.
        # The bedroom row is already in hand from above; only the sqft-keyed one
        # is a new lookup.
        opex_options = await self._opex_options(
            underwriting, opex_by_bedrooms=opex_by_bedrooms, area=area
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
                    deal_tag_options=deal_tag_options,
                    opex_options=opex_options,
                ),
            )
        )

    async def _opex_options(
        self, underwriting, *, opex_by_bedrooms, area
    ) -> list[OpexOption]:
        """The market's operating-expense catalog for this deal.

        Empty rather than partial when there is nothing to key on: no market, or
        no opex row at this bedroom count. A catalog of thirteen null amounts
        would read as "the market charges nothing", which is worse than showing
        no catalog at all — ``_opex_by_bedrooms`` has already logged why.
        """
        if not underwriting.market_id or opex_by_bedrooms is None:
            return []

        sqft = PrepareUwDataService().normalize_sqft(area)
        opex_by_size = (
            await self.opex_by_size_service.get_by_market_and_sqft(
                sqft=sqft, market_id=underwriting.market_id
            )
            if self.opex_by_size_service is not None and sqft is not None
            else None
        )
        return opex_catalog.build_opex_options(
            opex_by_bedrooms=opex_by_bedrooms,
            opex_by_size=opex_by_size,
            purchase_price=underwriting.purchase_price,
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
        source: str | None = None,
        search: str | None = None,
        min_purchase_price: Decimal | None = None,
        max_purchase_price: Decimal | None = None,
        min_total_oop: Decimal | None = None,
        max_total_oop: Decimal | None = None,
        min_l_cash_on_cash: Decimal | None = None,
        max_l_cash_on_cash: Decimal | None = None,
        min_m_cash_on_cash: Decimal | None = None,
        max_m_cash_on_cash: Decimal | None = None,
        min_h_cash_on_cash: Decimal | None = None,
        max_h_cash_on_cash: Decimal | None = None,
        min_created_at: date | None = None,
        max_created_at: date | None = None,
        min_deal_approved: date | None = None,
        max_deal_approved: date | None = None,
        sort_by: UnderwritingSortBy = UnderwritingSortBy.ID,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> GetUnderwritingsResult:
        items, total, pages = await self.repository.get_all_paginated(
            page=page,
            page_size=page_size,
            zpid=zpid,
            market_id=market_id,
            deal_status=deal_status,
            analyst_id=analyst_id,
            source=source,
            search=search,
            min_purchase_price=min_purchase_price,
            max_purchase_price=max_purchase_price,
            min_total_oop=min_total_oop,
            max_total_oop=max_total_oop,
            min_l_cash_on_cash=min_l_cash_on_cash,
            max_l_cash_on_cash=max_l_cash_on_cash,
            min_m_cash_on_cash=min_m_cash_on_cash,
            max_m_cash_on_cash=max_m_cash_on_cash,
            min_h_cash_on_cash=min_h_cash_on_cash,
            max_h_cash_on_cash=max_h_cash_on_cash,
            min_created_at=min_created_at,
            max_created_at=max_created_at,
            min_deal_approved=min_deal_approved,
            max_deal_approved=max_deal_approved,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        results = [self._to_result(underwriting) for underwriting in items]
        await self._hydrate_automated_zillow(items, results)
        await self._enrich(results)
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

    async def _enrich(self, results: list[GetUnderwritingResult]) -> None:
        """Post-read enrichment shared by the single-get, list, and simulation
        paths: reference-data labels, resolved analyst/approver users, and the
        market's realtor details."""
        await self._populate_reference_labels(results)
        await self._populate_user_refs(results)
        await self._populate_realtor_details(results)

    async def _populate_user_refs(self, results: list[GetUnderwritingResult]) -> None:
        """Resolve ``analyst`` / ``approver`` / ``owner`` from their ``*_id``s.

        One batched query for the distinct user ids across the page; no-op when
        no user repository is configured. Deleted or unknown ids leave the ref
        ``None`` (the raw ``*_id`` fields still carry the stored value).
        """
        if self.user_repository is None or not results:
            return
        user_ids = {
            user_id
            for result in results
            for user_id in (result.analyst_id, result.approver_id, result.owner_id)
            if user_id is not None
        }
        if not user_ids:
            return
        users = await self.user_repository.get_by_ids(user_ids)
        refs = {user.id: UserRef.model_validate(user) for user in users}
        for result in results:
            if result.analyst_id is not None:
                result.analyst = refs.get(result.analyst_id)
            if result.approver_id is not None:
                result.approver = refs.get(result.approver_id)
            if result.owner_id is not None:
                result.owner = refs.get(result.owner_id)

    async def _populate_realtor_details(
        self, results: list[GetUnderwritingResult]
    ) -> None:
        """Resolve ``realtor_details`` from the market's realtor_ids.

        Each distinct market on the page is fetched once, then all referenced
        realtors in one batched query. No-op when the market/realtor
        repositories aren't configured. Soft-deleted or unknown realtor ids
        drop out of the list; each market's realtor_ids order is preserved.
        """
        if (
            self.market_repository is None
            or self.realtor_repository is None
            or not results
        ):
            return
        market_ids = {r.market_id for r in results if r.market_id is not None}
        if not market_ids:
            return
        realtor_ids_by_market: dict[int, list[int]] = {}
        for market_id in market_ids:
            market = await self.market_repository.get_by_id(market_id)
            realtor_ids_by_market[market_id] = (
                market.realtor_ids or [] if market is not None else []
            )
        realtor_ids = {
            realtor_id for ids in realtor_ids_by_market.values() for realtor_id in ids
        }
        if not realtor_ids:
            return
        realtors = await self.realtor_repository.get_by_ids(realtor_ids)
        details = {
            realtor.id: UnderwritingRealtorDetail.model_validate(realtor)
            for realtor in realtors
        }
        for result in results:
            if result.market_id is None:
                continue
            result.realtor_details = [
                details[realtor_id]
                for realtor_id in realtor_ids_by_market.get(result.market_id, [])
                if realtor_id in details
            ]

    async def _populate_reference_labels(
        self, results: list[GetUnderwritingResult]
    ) -> None:
        """Resolve ``<field>_label`` for each tag slug from reference data."""
        await apply_reference_labels(results, self.reference_data_service)

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
            "property_taxes": detail.property_taxes,
            "zillow_property": detail.zillow_property,
            "analyst_notes": detail.analyst_notes,
            "construction_and_design_notes": detail.construction_and_design_notes,
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
            "id": item.id,
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
            "id": expense.id,
            "expense_name": expense.expense_name,
            "monthly_amount": expense.monthly_amount,
        }

    def _comp_set_data(self, comp) -> dict[str, Any]:
        return {
            "id": comp.id,
            "listing_url": comp.listing_url,
            "revenue": comp.revenue,
            "bedrooms": comp.bedrooms,
            "sleeps": comp.sleeps,
            "is_favourite": comp.is_favourite,
        }

    async def _zillow_from_listing(self, underwriting) -> tuple[Any, Any]:
        """Automated path: hydrate zillow data live from scheduled_listings.

        The second element is the listing's own bed count, kept solely as a
        fallback for rows predating ``underwritings.bedrooms``.
        """
        if not underwriting.zpid:
            logger.warning(
                "iron_bank.get_underwriting.no_zpid",
                underwriting_id=underwriting.id,
                detail="underwriting has no zpid — zillow data will be unavailable",
            )
            return None, None

        listing = await self.listings_service.get_by_zpid(underwriting.zpid)
        if listing is None:
            logger.warning(
                "iron_bank.get_underwriting.listing_not_found",
                underwriting_id=underwriting.id,
                zpid=underwriting.zpid,
                detail="no listing found for zpid — zillow data will be unavailable",
            )
            return None, None

        listing_details = await self.listing_details_service.get_by_zpid(
            underwriting.zpid
        )
        zillow_property = PrepareUwDataService()._transform_zillow_property(
            listing, listing_details
        )
        return zillow_property, listing.beds

    async def _zillow_from_stored(self, underwriting) -> tuple[Any, Any]:
        """Non-automated path: read zillow data persisted on uw_details.

        The second element is Zillow's own bed count, kept solely as a fallback
        for rows predating ``underwritings.bedrooms``.
        """
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

        return zillow_property, zillow_property.bedrooms

    async def _opex_by_bedrooms(self, underwriting, *, bedrooms):
        """The market's opex row for this underwriting's bedroom count.

        Keyed on ``underwritings.bedrooms`` (resolved by the caller) rather than
        on Zillow, so a deal whose bedroom count changed during underwriting
        gets the furnishing/shipping prices it was actually underwritten at.

        The ``market_id`` guard lives here, not in the zillow helpers: it only
        ever gated this lookup, and a market-less deal should still get its
        zillow data hydrated.
        """
        if not underwriting.market_id:
            logger.warning(
                "iron_bank.get_underwriting.no_market_id",
                underwriting_id=underwriting.id,
                detail="underwriting has no market_id — furnishings prices will be unavailable",
            )
            return None
        if bedrooms is None:
            logger.warning(
                "iron_bank.get_underwriting.no_bedrooms",
                underwriting_id=underwriting.id,
                detail="underwriting has no bedrooms — furnishings prices will be unavailable",
            )
            return None

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
