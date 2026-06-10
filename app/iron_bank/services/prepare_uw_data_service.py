from app.iron_bank.defaults import UW_CONFIG_DEFAULTS


class PrepareUwDataService:
    """Pure iron_bank calculation — assembles UW data from raw values.

    Cross-domain fetching lives in app.workflows.prepare_uw_data_job; this
    service must not import from other domains.
    """

    _SQFT_CHECKPOINTS = [1000, 1500, 2000, 2750, 3500, 4500]
    _OPEX_METADATA_FIELDS = {"id", "market_id", "market_slug", "bedrooms", "sqft"}
    _OPEX_CLEANING_FIELDS = {"cleaning_fee", "num_of_turns"}
    _OPEX_RANGED_FIELDS = {"pool_hot_tub_low", "pool_hot_tub_high", "furnishings_low", "furnishings_high"}

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
            "price": listing.price,
            "address": listing.address,
            "bedrooms": listing.beds,
            "bathrooms": listing.baths,
            "area": listing.area,
            "original_photos": listing_details.original_photos if listing_details else None,
            "lot_size_sqft": listing_details.lot_size_sqft if listing_details else None,
        }

    def _transform_opex_costs(self, opex_by_bedrooms, opex_by_size) -> dict:
        bedrooms_data = opex_by_bedrooms.model_dump() if opex_by_bedrooms is not None else {}
        size_data = opex_by_size.model_dump() if opex_by_size is not None else {}

        exclude = self._OPEX_METADATA_FIELDS | self._OPEX_CLEANING_FIELDS | self._OPEX_RANGED_FIELDS
        absolute = {k: v for k, v in {**bedrooms_data, **size_data}.items() if k not in exclude}

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
        }

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
    ) -> dict:
        amenities = [{
            "amenity_name": "Furnishings",
            "id": 0,
            "location": None,
            "notes": None,
            "price_tier_1": opex_by_bedrooms.furnishings_low if opex_by_bedrooms else None,
            "price_tier_2": None,
            "price_tier_3": opex_by_bedrooms.furnishings_high if opex_by_bedrooms else None,
        }] + [a.model_dump() for a in construction_amenities]

        config = UW_CONFIG_DEFAULTS.model_dump()
        if fred is not None:
            config["fred"] = {"value": fred.value / 100, "date": fred.date}

        return {
            "market_name": market.market_name if market else None,
            "market_id": market_id,
            "market_slug": market.market_slug if market else None,
            "zillow_property": self._transform_zillow_property(listing, listing_details),
            "opex": self._transform_opex_costs(opex_by_bedrooms, opex_by_size),
            "construction_amenities": amenities,
            "construction_remodeling": construction_remodeling,
            "config": config,
        }
