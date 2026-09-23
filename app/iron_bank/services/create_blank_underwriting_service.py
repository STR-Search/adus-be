from decimal import Decimal

import structlog

from app.iron_bank.schemas.save_underwriting import SaveUnderwritingResult
from app.iron_bank.services.create_underwriting_from_url_service import (
    MarketContextReader,
)
from app.iron_bank.services.non_automated_underwriting_payload_builder import (
    NonAutomatedUnderwritingPayloadBuilder,
)
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService

logger = structlog.get_logger(__name__)


class CreateBlankUnderwritingService:
    """Creates a draft underwriting with no listing behind it.

    The off-market / word-of-mouth entry point: load the market context for the
    caller's ``market_id`` (or a zeroed template when they didn't pick one),
    build a seeded save payload from the handful of fields the analyst typed,
    and persist it. No network calls. Returns the new underwriting id so the
    analyst can fill the rest in via update.

    Thin on purpose. ``CreateUnderwritingFromUrlService`` is heavy because of
    the external fetch and its guards; none of those have a subject here.

    **There is deliberately no duplicate guard**, including when a
    ``listing_url`` is supplied. It would now be possible to key one on that —
    the from-URL path's cheap pass does exactly that — but the URL here is a
    reference link to wherever the analyst found the deal, not an identity:
    two analysts working the same off-market address, or one deal linked from
    two places, are both legitimate. Its absence is a decision rather than an
    oversight, and adding one later means adding a 409 to this endpoint's
    contract, which today has none.

    Writing ``listing_url`` does, however, make a blank deal visible to two
    existing URL-keyed guards *elsewhere*, whenever the link happens to match a
    scraped listing's ``detail_url`` verbatim: ``POST
    /underwritings/from-zillow-url`` will 409 and redirect to it, and
    ``PrepareAndSaveUnderwritingJob._find_existing`` will skip the automated
    run for that listing. Both treat the blank deal as already covering the
    property, which is the intended reading — and it is the same behaviour that
    fallback was written for, since legacy null-zpid deals are matched by URL
    the same way.

    ``MarketContextReader`` is the Protocol from
    ``create_underwriting_from_url_service`` — structural rather than an import
    of the concrete job, because iron_bank must not import ``app/workflows``.
    The router wires ``PrepareUwDataJob.from_session(db)`` in.
    """

    def __init__(
        self,
        save_service: SaveUnderwritingService,
        market_context_reader: MarketContextReader,
        builder: NonAutomatedUnderwritingPayloadBuilder | None = None,
    ):
        self.save_service = save_service
        self.market_context_reader = market_context_reader
        self.builder = builder or NonAutomatedUnderwritingPayloadBuilder()

    async def create(
        self,
        *,
        purchase_price: Decimal,
        listing_url: str | None = None,
        market_id: int | None = None,
        bedrooms: int | None = None,
        bathrooms: Decimal | None = None,
        current_user_id: int | None = None,
    ) -> SaveUnderwritingResult:
        # How often either is supplied is the evidence behind the pending
        # product decision on making bedrooms mandatory: without one the
        # (market_id, bedrooms) opex lookup misses and the market's opex row,
        # cleaning cost, property taxes and land/appreciation config are all
        # lost, recoverable only via GET /underwritings/{id}/bedroom-context.
        logger.info(
            "iron_bank.create_blank_underwriting.requested",
            has_market_id=market_id is not None,
            has_bedrooms=bedrooms is not None,
            market_id=market_id,
            bedrooms=bedrooms,
        )

        # area is unknown at create, so the sqft-keyed opex rows (internet,
        # utilities, pest control) seed blank on every blank deal.
        context = await self.market_context_reader.build_market_context(
            market_id=market_id, bedrooms=bedrooms, area=None
        )
        logger.info(
            "iron_bank.create_blank_underwriting.market_context_loaded",
            requested_market_id=market_id,
            resolved_market_id=context.market_id,
            is_template=context.market_id is None,
            opex_row_count=len(context.opex.absolute),
        )

        payload = self.builder.build_blank(
            purchase_price=purchase_price,
            market_context=context,
            listing_url=listing_url,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            current_user_id=current_user_id,
        )
        return await self.save_service.save(payload)
