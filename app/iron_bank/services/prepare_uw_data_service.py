from decimal import Decimal

from app.iron_bank.defaults import UW_CONFIG_DEFAULTS
from app.iron_bank.schemas.prepare_uw import MarketContext, PrepareUwDataResult


class PrepareUwDataService:
    """Pure iron_bank calculation — assembles UW data from raw values.

    Cross-domain fetching lives in app.workflows.prepare_uw_data_job; this
    service must not import from other domains.
    """

    # Spread applied over the FRED 30y fixed rate to derive the UW interest rate.
    _INTEREST_RATE_SPREAD_OVER_FRED = 0.0035
    _SQFT_CHECKPOINTS = [1000, 1500, 2000, 2750, 3500, 4500]
    _OPEX_METADATA_FIELDS = {"id", "market_id", "market_slug", "bedrooms", "sqft"}
    _OPEX_CLEANING_FIELDS = {"cleaning_fee", "num_of_turns"}
    _OPEX_RANGED_FIELDS = {
        "pool_hot_tub_low",
        "pool_hot_tub_high",
        "furnishings_low",
        "furnishings_mid",
        "furnishings_high",
    }
    _OPEX_CONFIG_FIELDS = {"land_value", "appreciation"}
    # Opex columns that are percentages of purchase price, not monthly dollar
    # amounts; the payload builder resolves them against the listing price.
    _OPEX_PCT_OF_PURCHASE_FIELDS = {"property_taxes"}
    # Opex columns that are surfaced as amenity options (see
    # build_amenities_options) rather than monthly operating expenses.
    _OPEX_AMENITY_FIELDS = {"consolidated_shipping"}

    # Synthetic amenity options prepended to the construction_costs_amenities
    # catalog by build_amenities_options. They are not catalog rows, so they
    # carry non-positive sentinel ids that cannot collide with real ones.
    FURNISHINGS_OPTION_ID = 0
    CONSOLIDATED_SHIPPING_OPTION_ID = -1
    STR_CRIBS_PROJECT_MANAGEMENT_OPTION_ID = -2
    # Seeded on every underwriting regardless of market, in this order.
    SEEDED_AMENITY_OPTION_IDS = (
        FURNISHINGS_OPTION_ID,
        CONSOLIDATED_SHIPPING_OPTION_ID,
        STR_CRIBS_PROJECT_MANAGEMENT_OPTION_ID,
    )

    # A non-automated underwriting can be created without a market. We still owe
    # the analyst the full set of opex and rehab rows to fill in, so the shape is
    # borrowed from this market and every amount is then zeroed out. See
    # to_template_market_context.
    TEMPLATE_MARKET_ID = 1

    # Appreciation for a market-less deal. Kept in step with
    # SaveUnderwritingService._DEFAULT_ANNUAL_RE_APPRECIATION_PCT, which the
    # forecast falls back to when there is no market rate to read.
    TEMPLATE_ANNUAL_RE_APPRECIATION_PCT = 0.0425

    def normalize_sqft(self, area: int | None) -> int | None:
        if area is None:
            return None
        for checkpoint in self._SQFT_CHECKPOINTS:
            if area <= checkpoint:
                return checkpoint
        return self._SQFT_CHECKPOINTS[-1]

    def _transform_zillow_property(self, listing, listing_details) -> dict:
        return {
            "id": listing.zpid,
            "url": listing.detail_url,
            "thumbnail": listing.img_src,
            "price": getattr(listing, "unformatted_price", None) or listing.price,
            "address": listing.address,
            "bedrooms": listing.beds,
            "bathrooms": listing.baths,
            "area": listing.area,
            "original_photos": (
                listing_details.original_photos if listing_details else None
            ),
            "lot_size_sqft": listing_details.lot_size_sqft if listing_details else None,
            "description": listing_details.description if listing_details else None,
        }

    def _transform_opex_costs(self, opex_by_bedrooms, opex_by_size) -> dict:
        bedrooms_data = (
            opex_by_bedrooms.model_dump() if opex_by_bedrooms is not None else {}
        )
        size_data = opex_by_size.model_dump() if opex_by_size is not None else {}

        exclude = (
            self._OPEX_METADATA_FIELDS
            | self._OPEX_CLEANING_FIELDS
            | self._OPEX_RANGED_FIELDS
            | self._OPEX_CONFIG_FIELDS
            | self._OPEX_AMENITY_FIELDS
            | self._OPEX_PCT_OF_PURCHASE_FIELDS
        )
        absolute = {
            k: v for k, v in {**bedrooms_data, **size_data}.items() if k not in exclude
        }

        return {
            "cleaning": {
                "fee": bedrooms_data.get("cleaning_fee"),
                "num_of_turns": bedrooms_data.get("num_of_turns"),
            },
            "ranged": {
                "pool_hot_tub": {
                    "low": bedrooms_data.get("pool_hot_tub_low"),
                    "high": bedrooms_data.get("pool_hot_tub_high"),
                },
            },
            "absolute": absolute,
            "property_tax_pct": bedrooms_data.get("property_taxes"),
        }

    def _apply_opex_config_values(
        self, config: dict, opex_by_bedrooms, opex_by_size
    ) -> None:
        bedrooms_data = (
            opex_by_bedrooms.model_dump() if opex_by_bedrooms is not None else {}
        )
        size_data = opex_by_size.model_dump() if opex_by_size is not None else {}
        opex_config = {**bedrooms_data, **size_data}

        if opex_config.get("land_value") is not None:
            config["land_assumptions"] = opex_config["land_value"]
        if opex_config.get("appreciation") is not None:
            config["annual_re_appreciation_pct"] = opex_config["appreciation"]

    @staticmethod
    def build_amenities_options(
        opex_by_bedrooms, construction_amenities: list, str_cribs_fee=None
    ) -> list[dict]:
        furnishings = {
            "amenity_name": "Furnishings",
            "id": PrepareUwDataService.FURNISHINGS_OPTION_ID,
            "location": None,
            "notes": None,
            "price_tier_1": (
                opex_by_bedrooms.furnishings_low if opex_by_bedrooms else None
            ),
            "price_tier_2": (
                opex_by_bedrooms.furnishings_mid if opex_by_bedrooms else None
            ),
            "price_tier_3": (
                opex_by_bedrooms.furnishings_high if opex_by_bedrooms else None
            ),
        }
        consolidated_shipping = {
            "amenity_name": "Consolidated Shipping",
            "id": PrepareUwDataService.CONSOLIDATED_SHIPPING_OPTION_ID,
            "location": None,
            "notes": None,
            "price_tier_1": (
                opex_by_bedrooms.consolidated_shipping if opex_by_bedrooms else None
            ),
            "price_tier_2": (
                opex_by_bedrooms.consolidated_shipping if opex_by_bedrooms else None
            ),
            "price_tier_3": (
                opex_by_bedrooms.consolidated_shipping if opex_by_bedrooms else None
            ),
        }
        str_cribs_project_management = {
            "amenity_name": "STR Cribs - Project Management",
            "id": PrepareUwDataService.STR_CRIBS_PROJECT_MANAGEMENT_OPTION_ID,
            "location": None,
            "notes": None,
            "price_tier_1": (str_cribs_fee.fee if str_cribs_fee else None),
            "price_tier_2": (str_cribs_fee.fee if str_cribs_fee else None),
            "price_tier_3": (str_cribs_fee.fee if str_cribs_fee else None),
        }
        return [furnishings, consolidated_shipping, str_cribs_project_management] + [
            a.model_dump() for a in construction_amenities
        ]

    @staticmethod
    def _must_have_amenity_ids(market) -> list[int]:
        """Amenity ids this market requires, in the order the market lists them.

        ``market.must_have_amenities`` arrives already resolved against the
        amenity catalog, so ids pointing at soft-deleted rows have been dropped
        upstream.
        """
        if market is None:
            return []
        return [ref.id for ref in market.must_have_amenities or []]

    def prepare_market_context(
        self,
        *,
        market,
        market_id: int | None,
        opex_by_bedrooms,
        opex_by_size,
        construction_amenities: list,
        construction_remodeling: list,
        fred,
        str_cribs_fee=None,
    ) -> MarketContext:
        """Assemble the market-derived half of a draft underwriting.

        Property-agnostic on purpose: the opex/amenity rows have already been
        looked up by bedrooms and sqft upstream, so nothing here needs the
        listing itself. Both the automated flow (via ``prepare``) and the
        non-automated create-from-URL flow build their opex and rehab line items
        off this.
        """
        amenities = self.build_amenities_options(
            opex_by_bedrooms, construction_amenities, str_cribs_fee
        )

        config = UW_CONFIG_DEFAULTS.model_dump()
        if fred is not None:
            fred_rate = fred.value / 100
            config["fred"] = {"value": fred_rate, "date": fred.date}
            # Underwrite at 0.35% above the current FRED 30y fixed rate.
            config["interest_rate"] = fred_rate + self._INTEREST_RATE_SPREAD_OVER_FRED
        self._apply_opex_config_values(config, opex_by_bedrooms, opex_by_size)

        return MarketContext.model_validate(
            {
                "market_name": market.market_name if market else None,
                "market_id": market_id,
                "market_slug": market.market_slug if market else None,
                "opex": self._transform_opex_costs(opex_by_bedrooms, opex_by_size),
                "construction_amenities": amenities,
                "construction_remodeling": [
                    r.model_dump() for r in construction_remodeling
                ],
                "must_have_amenity_ids": self._must_have_amenity_ids(market),
                "config": config,
            }
        )

    @classmethod
    def to_template_market_context(cls, context: MarketContext) -> MarketContext:
        """Strip a real market's figures out of a context, keeping its shape.

        Used when a non-automated underwriting is created without a market. The
        caller loads the context for ``TEMPLATE_MARKET_ID`` — so the opex and
        amenity rows exist and are keyed to the property's bedrooms/sqft — and
        this zeroes every amount so the analyst fills them in from scratch:

        - all opex amounts (cleaning, pool/hot tub, absolute rows, the property
          tax rate) become 0, with the keys kept so every row still renders
        - ``must_have_amenity_ids`` is dropped; a market-less deal has none
        - the three always-seeded amenity options (furnishings, consolidated
          shipping, the STR Cribs fee) keep their names and ids but lose their
          prices. The rest of the catalog passes through untouched — it is the
          analyst's picklist, not seeded line items.
        - market-derived config reverts to defaults, except appreciation, which
          is pinned to ``TEMPLATE_ANNUAL_RE_APPRECIATION_PCT`` to match the rate
          the forecast falls back to for a market-less deal. The live FRED rate
          and the interest rate derived from it are not market-specific, so they
          stay.

        The identity fields are nulled last: the resulting underwriting is
        genuinely market-less, not silently attached to the template market.
        """
        zero = Decimal("0")
        template = context.model_copy(deep=True)

        template.opex.cleaning.fee = zero
        template.opex.cleaning.num_of_turns = zero
        template.opex.ranged.pool_hot_tub.low = zero
        template.opex.ranged.pool_hot_tub.high = zero
        template.opex.property_tax_pct = zero
        template.opex.absolute = {key: zero for key in template.opex.absolute}

        template.must_have_amenity_ids = []
        for option in template.construction_amenities:
            if option.id in cls.SEEDED_AMENITY_OPTION_IDS:
                option.price_tier_1 = zero
                option.price_tier_2 = zero
                option.price_tier_3 = zero

        defaults = UW_CONFIG_DEFAULTS.model_copy()
        defaults.fred = template.config.fred
        defaults.interest_rate = template.config.interest_rate
        defaults.annual_re_appreciation_pct = cls.TEMPLATE_ANNUAL_RE_APPRECIATION_PCT
        template.config = defaults

        template.market_id = None
        template.market_name = None
        template.market_slug = None
        return template

    def prepare(
        self,
        *,
        listing,
        listing_details,
        market,
        market_id: int | None,
        opex_by_bedrooms,
        opex_by_size,
        construction_amenities: list,
        construction_remodeling: list,
        fred,
        str_cribs_fee=None,
    ) -> PrepareUwDataResult:
        context = self.prepare_market_context(
            market=market,
            market_id=market_id,
            opex_by_bedrooms=opex_by_bedrooms,
            opex_by_size=opex_by_size,
            construction_amenities=construction_amenities,
            construction_remodeling=construction_remodeling,
            fred=fred,
            str_cribs_fee=str_cribs_fee,
        )

        return PrepareUwDataResult.model_validate(
            {
                **context.model_dump(),
                "zillow_property": self._transform_zillow_property(
                    listing, listing_details
                ),
                "street": listing.address_street,
                "city": listing.address_city,
                "state": listing.address_state,
            }
        )
