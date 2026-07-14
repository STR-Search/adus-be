from app.iron_bank.defaults import UW_CONFIG_DEFAULTS
from app.iron_bank.schemas.prepare_uw import PrepareUwDataResult


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
            "id": 0,
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
            "id": -1,
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
            "id": -2,
            "location": None,
            "notes": None,
            "price_tier_1": (str_cribs_fee.fee if str_cribs_fee else None),
            "price_tier_2": (str_cribs_fee.fee if str_cribs_fee else None),
            "price_tier_3": (str_cribs_fee.fee if str_cribs_fee else None),
        }
        return [furnishings, consolidated_shipping, str_cribs_project_management] + [
            a.model_dump() for a in construction_amenities
        ]

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

        return PrepareUwDataResult.model_validate(
            {
                "market_name": market.market_name if market else None,
                "market_id": market_id,
                "market_slug": market.market_slug if market else None,
                "zillow_property": self._transform_zillow_property(
                    listing, listing_details
                ),
                "opex": self._transform_opex_costs(opex_by_bedrooms, opex_by_size),
                "construction_amenities": amenities,
                "construction_remodeling": [
                    r.model_dump() for r in construction_remodeling
                ],
                "config": config,
            }
        )
