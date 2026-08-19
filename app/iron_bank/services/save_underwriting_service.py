from decimal import Decimal
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
from app.iron_bank.schemas.underwriting import (
    MULTI_SELECT_TAG_FIELDS,
    SINGLE_SELECT_TAG_FIELDS,
)
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator
from app.markets.schemas.market import MarketKeysMasterSchema
from app.zillow.models.scheduled_listings import ScheduledListing

logger = structlog.get_logger(__name__)


class MarketReader(Protocol):
    async def get_by_id(self, market_id: int) -> MarketKeysMasterSchema | None: ...


class ListingReader(Protocol):
    async def get_by_zpid(self, zpid: str) -> ScheduledListing | None: ...


class ReferenceDataValidator(Protocol):
    async def validate_active_option(
        self, domain: str | None, set_code: str, key: str | None
    ) -> None: ...


class CleanedDataRevenueReader(Protocol):
    async def get_revenue_potential_percentiles(
        self,
        *,
        key_market: str,
        bedrooms: int,
    ) -> RevenuePotentialPercentiles | None: ...


class OpexByBedroomsReader(Protocol):
    """Satisfied by ``app.markets.services.opex_service.OpexByBedroomsService``."""

    async def get_by_market_and_bedrooms(
        self, bedrooms: int, market_id: int | None = None
    ) -> Any | None: ...


class SaveUnderwritingService:
    # Fallback annual RE appreciation, used when the market's own rate can't be
    # resolved (no opex row, or no opex reader wired). 4.25% is the most common
    # rate across seeded markets, which range 4.00%-5.50%.
    _DEFAULT_ANNUAL_RE_APPRECIATION_PCT = Decimal("0.0425")

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
        reference_data_service: ReferenceDataValidator | None = None,
        opex_service: OpexByBedroomsReader | None = None,
    ):
        self.repository = repository
        self.calculator = calculator or UnderwritingCalculator()
        self.market_service = market_service
        self.listings_service = listings_service
        self.cleaned_data_service = cleaned_data_service
        self.reference_data_service = reference_data_service
        # Supplies the market's annual RE appreciation rate for the forecast;
        # without it the fallback constant applies.
        self.opex_service = opex_service

    async def save(self, payload: SaveUnderwritingPayload) -> SaveUnderwritingResult:
        data = payload.model_dump(exclude_unset=True)

        underwriting_data = {
            key: value for key, value in data.items() if key not in self._CHILD_FIELDS
        }
        await self._validate_reference_data_fields(underwriting_data)
        await self._apply_listing_boolean_fields(underwriting_data, payload)
        tax_data = self._build_tax_data(payload)
        bedrooms = await self._resolve_bedrooms_for_save(payload)
        # Persist the resolved values, not just use them: the underwriting row
        # is the source of truth from creation onwards, and resolving centrally
        # here guarantees the invariant even for direct API callers that send
        # neither field.
        underwriting_data["bedrooms"] = bedrooms
        underwriting_data["bathrooms"] = await self._resolve_bathrooms_for_save(payload)
        detail_data = await self._build_detail_data(
            payload,
            tax_data,
            market_id=payload.market_id,
            bedrooms=bedrooms,
        )
        self._apply_calculated_underwriting_fields(
            underwriting_data,
            detail_data,
            payload.optimization_list,
        )

        logger.debug(
            "save.repository.create: start",
            optimization_count=len(payload.optimization_list),
            operating_expenses_count=len(payload.operating_expenses),
            comp_set_count=len(payload.comp_set),
            has_detail_data=detail_data is not None,
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
        logger.debug(
            "save.repository.create: complete",
            underwriting_id=underwriting.id,
        )
        return SaveUnderwritingResult(underwriting_id=underwriting.id)

    async def _validate_reference_data_fields(
        self, underwriting_data: dict[str, Any]
    ) -> None:
        """Reject any tag slug that isn't an active option in its reference set.

        No-op when no reference-data service is configured (e.g. internal
        builders that bypass user input). Each tag field name doubles as its
        reference ``set_code`` under ``domain = "iron_bank"``. Single-select
        fields hold one slug; multi-select fields hold a list of slugs, each
        validated individually.
        """
        if self.reference_data_service is None:
            return
        for field in SINGLE_SELECT_TAG_FIELDS:
            if field in underwriting_data:
                await self.reference_data_service.validate_active_option(
                    "iron_bank", field, underwriting_data[field]
                )
        for field in MULTI_SELECT_TAG_FIELDS:
            if field in underwriting_data:
                for slug in underwriting_data[field] or []:
                    await self.reference_data_service.validate_active_option(
                        "iron_bank", field, slug
                    )

    def _without_empty_values(self, data: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in data.items() if value is not None}

    async def _apply_listing_boolean_fields(
        self,
        underwriting_data: dict[str, Any],
        payload: SaveUnderwritingPayload,
    ) -> None:
        if self.listings_service is None or payload.zpid is None:
            return

        listing = await self.listings_service.get_by_zpid(payload.zpid)
        if listing is None:
            return

        underwriting_data["property_pending"] = listing.home_status != "FOR_SALE"

    async def _build_detail_data(
        self,
        payload: SaveUnderwritingPayload,
        tax_data: dict | None = None,
        *,
        market_id: int | None = None,
        bedrooms: int | None = None,
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
                market_id=market_id,
                bedrooms=bedrooms,
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

        zillow_property = await self._resolve_zillow_property(payload)
        if zillow_property is not None:
            detail_data["zillow_property"] = zillow_property

        return detail_data

    async def _resolve_zillow_property(
        self, payload: SaveUnderwritingPayload
    ) -> dict[str, Any] | None:
        """Resolve the zillow_property persisted on uw_details.

        Client/builder-provided only: non-automated underwritings carry
        ``details.zillow_property`` (built upfront from the external API at
        creation time — see CreateUnderwritingFromUrlService). Automated
        underwritings hydrate zillow data live from scheduled_listings on read,
        so they don't carry it here. No network calls happen during save.
        """
        if payload.details is None or payload.details.zillow_property is None:
            return None
        return payload.details.zillow_property.model_dump(exclude_unset=True)

    async def _resolve_bedrooms_for_save(
        self, payload: SaveUnderwritingPayload
    ) -> int | None:
        """Resolve the bedroom count for the row's own column and the Airbnb lookup.

        ``payload.bedrooms`` is the analyst-owned assumption and wins; both
        payload builders set it at creation. The Zillow fallbacks exist for
        direct ``POST /iron-bank/underwritings`` callers that don't send it —
        non-automated payloads carry the property data inline on
        ``details.zillow_property``, automated ones only carry a ``zpid``.
        """
        if payload.bedrooms is not None:
            return payload.bedrooms

        if (
            payload.details is not None
            and payload.details.zillow_property is not None
            and payload.details.zillow_property.bedrooms is not None
        ):
            return payload.details.zillow_property.bedrooms

        listing = await self._listing_for_save(payload)
        if listing is not None:
            return listing.beds

        return None

    async def _resolve_bathrooms_for_save(
        self, payload: SaveUnderwritingPayload
    ) -> Decimal | None:
        """Bathrooms counterpart to ``_resolve_bedrooms_for_save``.

        Drives no lookup — it exists so the column is populated on every
        creation path. ``scheduled_listings.baths`` is a float, so it is
        converted for the Numeric column.
        """
        if payload.bathrooms is not None:
            return payload.bathrooms

        if (
            payload.details is not None
            and payload.details.zillow_property is not None
            and payload.details.zillow_property.bathrooms is not None
        ):
            return payload.details.zillow_property.bathrooms

        listing = await self._listing_for_save(payload)
        if listing is not None and listing.baths is not None:
            return Decimal(str(listing.baths))

        return None

    async def _listing_for_save(self, payload: SaveUnderwritingPayload):
        if self.listings_service is None or payload.zpid is None:
            return None
        return await self.listings_service.get_by_zpid(payload.zpid)

    async def _build_forecasted_revenue_input(
        self,
        *,
        market_id: int | None,
        bedrooms: int | None,
    ) -> ForecastedRevenueInput | None:
        """Estimate forecasted revenue from Airbnb comps keyed by (market, beds).

        Returns ``None`` (with an explanatory log) for any condition under which
        the estimate can't be produced, rather than raising — a missing estimate
        leaves the field unpopulated for the analyst to fill, and must not break
        a save or an update. ``bedrooms`` is resolved by the caller (from
        ``scheduled_listings`` for automated underwritings, or from the stored
        ``zillow_property`` for non-automated ones), so this method is agnostic
        to where the property data lives.
        """
        if self.market_service is None or self.cleaned_data_service is None:
            logger.debug(
                "_build_forecasted_revenue_input: skipping — market or cleaned-data "
                "service not configured",
                has_market_service=self.market_service is not None,
                has_cleaned_data_service=self.cleaned_data_service is not None,
            )
            return None

        if market_id is None or bedrooms is None:
            logger.debug(
                "_build_forecasted_revenue_input: skipping — market_id and bedrooms "
                "are both required for the Airbnb revenue lookup; forecasted_revenue "
                "will not be estimated",
                market_id=market_id,
                bedrooms=bedrooms,
            )
            return None

        market = await self.market_service.get_by_id(market_id)
        logger.debug(
            "_build_forecasted_revenue_input: market lookup",
            market_id=market_id,
            market_name_current=market.market_name_current if market else None,
        )
        if market is None or market.market_name_current is None:
            logger.warning(
                "_build_forecasted_revenue_input: skipping — no market_name_current "
                "for market_id; forecasted_revenue will not be estimated",
                market_id=market_id,
            )
            return None

        percentiles = await self.cleaned_data_service.get_revenue_potential_percentiles(
            key_market=market.market_name_current,
            bedrooms=bedrooms,
        )
        logger.debug(
            "_build_forecasted_revenue_input: percentiles lookup",
            key_market=market.market_name_current,
            bedrooms=bedrooms,
            percentiles_low=percentiles.low if percentiles else None,
            percentiles_mid=percentiles.mid if percentiles else None,
            percentiles_high=percentiles.high if percentiles else None,
        )
        if percentiles is None:
            logger.warning(
                "_build_forecasted_revenue_input: skipping — no Airbnb revenue "
                "percentiles for market/bedrooms; forecasted_revenue will not be "
                "estimated",
                key_market=market.market_name_current,
                bedrooms=bedrooms,
            )
            return None

        forecasted_revenue_input = ForecastedRevenueInput.model_validate(
            {
                "co_hosting_fee_pct": 0,
                "annual_re_appreciation_pct": await self._resolve_appreciation_pct(
                    market_id=market_id,
                    bedrooms=bedrooms,
                ),
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

    async def _resolve_appreciation_pct(
        self,
        *,
        market_id: int | None,
        bedrooms: int | None,
    ) -> Decimal:
        """The market's annual RE appreciation rate, keyed like the comps lookup.

        ``markets.opex_by_bedrooms.appreciation`` is stored as a fraction (the
        seeder divides the CSV percentage by 100), so it drops straight into
        ``annual_re_appreciation_pct`` with no conversion. It is keyed by
        (market, bedrooms) — the same key the Airbnb comps use — though in
        practice nearly every market sets one rate across all bedroom counts.

        Falls back to ``_DEFAULT_ANNUAL_RE_APPRECIATION_PCT`` whenever the rate
        can't be resolved: no opex reader wired, no row for this
        market/bedrooms, or a null ``appreciation`` on the row. A missing rate
        must not cost us the whole forecast.
        """
        if self.opex_service is None or market_id is None or bedrooms is None:
            return self._DEFAULT_ANNUAL_RE_APPRECIATION_PCT

        opex = await self.opex_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms, market_id=market_id
        )
        appreciation = getattr(opex, "appreciation", None) if opex else None
        if appreciation is None:
            logger.info(
                "_resolve_appreciation_pct: no market appreciation rate — using the "
                "default",
                market_id=market_id,
                bedrooms=bedrooms,
                default_pct=self._DEFAULT_ANNUAL_RE_APPRECIATION_PCT,
            )
            return self._DEFAULT_ANNUAL_RE_APPRECIATION_PCT

        logger.debug(
            "_resolve_appreciation_pct: using the market's appreciation rate",
            market_id=market_id,
            bedrooms=bedrooms,
            appreciation_pct=appreciation,
        )
        return appreciation

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
        if forecasted_revenue is None:
            logger.debug(
                "_apply_calculated_underwriting_fields: no forecasted_revenue — "
                "low/mid/high_gross_revenue, total_oop, prr, budget_to_pp and "
                "cash_on_cash will not be calculated. forecasted_revenue requires "
                "Airbnb comps (market_id + bedrooms); fill these in via update.",
                has_purchase_details=purchase_details is not None,
            )
            return

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

        if purchase_details is None:
            logger.debug(
                "_apply_calculated_underwriting_fields: forecasted_revenue present "
                "but no purchase_details — total_oop, prr, budget_to_pp and "
                "cash_on_cash will not be calculated (they need purchase_price and "
                "financing terms).",
            )
            return

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
        underwriting_data["budget_to_pp"] = self.calculator.calculate_budget_to_pp(
            total_oop=total_oop,
            purchase_price=purchase_details["purchase_price"],
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
