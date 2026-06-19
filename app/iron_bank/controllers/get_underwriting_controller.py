from typing import Any

from fastapi import HTTPException

from app.core.logger import logger
from app.iron_bank.schemas.get_underwriting import (
    ConstructionAmenityOption,
    ConstructionRemodelingOption,
    EditContextData,
    EditContextualData,
    GetUnderwritingEditContextResult,
    GetUnderwritingsResult,
)
from app.iron_bank.services.get_underwriting_service import GetUnderwritingService
from app.iron_bank.services.prepare_uw_data_service import PrepareUwDataService


class GetUnderwritingController:
    def __init__(
        self,
        service: GetUnderwritingService,
        construction_amenities_service: Any = None,
        construction_remodeling_service: Any = None,
        listings_service: Any = None,
        listing_details_service: Any = None,
        opex_by_bedrooms_service: Any = None,
    ):
        self.service = service
        self.construction_amenities_service = construction_amenities_service
        self.construction_remodeling_service = construction_remodeling_service
        self.listings_service = listings_service
        self.listing_details_service = listing_details_service
        self.opex_by_bedrooms_service = opex_by_bedrooms_service

    async def get_underwritings(
        self,
        *,
        page: int,
        page_size: int,
        zpid: str | None = None,
        market_id: int | None = None,
    ) -> GetUnderwritingsResult:
        try:
            return await self.service.get_all(
                page=page,
                page_size=page_size,
                zpid=zpid,
                market_id=market_id,
            )
        except Exception as e:
            logger.error(
                "iron_bank.get_underwritings.error",
                page=page,
                page_size=page_size,
                zpid=zpid,
                market_id=market_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwritings")

    async def get_underwriting(
        self, underwriting_id: int
    ) -> GetUnderwritingEditContextResult:
        try:
            underwriting = await self.service.get(underwriting_id)

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

            amenities = await self.construction_amenities_service.get_all()
            remodeling = await self.construction_remodeling_service.get_all()
            amenity_options = PrepareUwDataService.build_amenities_options(
                opex_by_bedrooms, amenities
            )

            return GetUnderwritingEditContextResult(
                data=EditContextData(
                    underwriting=underwriting,
                    contextual=EditContextualData(
                        zillow_property=zillow_property,
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
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(
                "iron_bank.get_underwriting.error",
                underwriting_id=underwriting_id,
                error=str(e),
            )
            raise HTTPException(status_code=500, detail="Failed to fetch underwriting")

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
            underwriting, bedrooms=zillow_property.get("bedrooms")
        )
        return zillow_property, opex_by_bedrooms

    async def _opex_by_bedrooms(self, underwriting, *, bedrooms):
        opex_by_bedrooms = await self.opex_by_bedrooms_service.get_by_market_and_bedrooms(
            bedrooms=bedrooms, market_id=underwriting.market_id
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
