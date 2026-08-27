from typing import Any, Protocol

import structlog

from app.iron_bank.schemas.prepare_uw import MarketContext
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingResult
from app.iron_bank.services.non_automated_underwriting_payload_builder import (
    NonAutomatedUnderwritingPayloadBuilder,
)
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService

logger = structlog.get_logger(__name__)


class UnderwritingAlreadyExistsError(Exception):
    """Raised when an underwriting already exists for the given listing URL."""

    def __init__(self, underwriting_id: int):
        self.underwriting_id = underwriting_id
        super().__init__(
            f"An underwriting already exists for this property "
            f"(underwriting_id={underwriting_id})"
        )


class ListingNotScrapedError(Exception):
    """Raised when the property never landed in ``zillow.scheduled_listings``.

    Fetching property details also persists the listing upstream, so a missing
    row means the scrape did not complete for this URL. Without it the zpid FK
    cannot be satisfied, and the deal would be created detached from the listing
    that every downstream job keys on.
    """

    def __init__(self, url: str, zpid: str | None):
        self.url = url
        self.zpid = zpid
        super().__init__(
            "This listing could not be scraped, so it is not available yet. "
            "Please try again shortly."
        )


class ListingMarketMismatchError(Exception):
    """Raised when the requested market contradicts the listing's own market.

    ``scheduled_listings.zpid`` is the primary key and ``preset_id`` is NOT
    NULL, so a property sits under exactly one preset and therefore under
    exactly one market. Seeding a deal from a different market's context would
    key its opex and rehab line items to a market the listing does not belong
    to, so the analyst is sent back the market to re-submit with.
    """

    def __init__(
        self,
        *,
        requested_market_id: int | None,
        listing_market_id: int,
        listing_market_name: str | None = None,
        zpid: str | None,
    ):
        self.requested_market_id = requested_market_id
        self.listing_market_id = listing_market_id
        self.listing_market_name = listing_market_name
        self.zpid = zpid
        market = (
            f"{listing_market_name} (market_id={listing_market_id})"
            if listing_market_name
            else f"market {listing_market_id}"
        )
        super().__init__(
            f"This listing already belongs to {market}. "
            f"Re-submit with market_id={listing_market_id}."
        )


class ZillowPropertyReader(Protocol):
    async def fetch_property_details(
        self, *, url: str, market_id: int | None = None
    ) -> dict[str, Any] | None: ...


class ExistingUnderwritingReader(Protocol):
    async def get_by_listing_url(self, listing_url: str) -> Any | None: ...


class ListingReader(Protocol):
    """Satisfied by ``app.zillow.services.scheduled_listings_service``."""

    async def get_by_zpid(self, zpid: str) -> Any | None: ...

    async def get_by_detail_url(self, detail_url: str) -> Any | None: ...


class MarketNameReader(Protocol):
    """Satisfied by ``app.markets.services.market_service.MarketService``.

    Structural, not imported: iron_bank must not import the markets domain, so
    the router wires the concrete service in.
    """

    async def get_market_name_current(self, market_id: int) -> str | None: ...


class MarketContextReader(Protocol):
    """Satisfied by ``app.workflows.prepare_uw_data_job.PrepareUwDataJob``.

    Structural, not imported: the market/opex/amenity lookups live in the
    workflows layer because they cross domains, and iron_bank must not import
    back into it. The router does the wiring.
    """

    async def build_market_context(
        self, *, market_id: int | None, bedrooms: int | None, area: int | None
    ) -> MarketContext: ...


class CreateUnderwritingFromUrlService:
    """Creates a draft non-automated underwriting from a Zillow URL.

    Orchestrates the whole non-automated entry point: guard against duplicates
    by listing URL, guard against a ``market_id`` the listing contradicts,
    fetch property details from the external API (passing the analyst's
    ``market_id`` along with the URL), load the market context for that
    ``market_id`` (or a zeroed template when they didn't pick one), build
    a seeded save payload, and persist it via the
    generic save service. Saving itself performs no network calls. Returns the
    new underwriting id so the analyst can start filling it in via update.

    The market guard runs twice, on purpose: once before the fetch keyed on the
    URL (cheap, but only when the pasted URL matches the scraper's stored
    ``detail_url``) and once after it keyed on the zpid (authoritative, but the
    external call is already spent). The first is an optimisation; the second is
    the one that actually holds the invariant.
    """

    def __init__(
        self,
        zillow_property_service: ZillowPropertyReader,
        save_service: SaveUnderwritingService,
        underwriting_reader: ExistingUnderwritingReader,
        market_context_reader: MarketContextReader | None = None,
        builder: NonAutomatedUnderwritingPayloadBuilder | None = None,
        listings_service: ListingReader | None = None,
        market_name_reader: MarketNameReader | None = None,
    ):
        self.zillow_property_service = zillow_property_service
        self.save_service = save_service
        self.underwriting_reader = underwriting_reader
        self.market_context_reader = market_context_reader
        self.builder = builder or NonAutomatedUnderwritingPayloadBuilder()
        self.listings_service = listings_service
        self.market_name_reader = market_name_reader

    async def create(
        self,
        *,
        url: str,
        market_id: int | None = None,
        current_user_id: int | None = None,
    ) -> SaveUnderwritingResult:
        # Idempotency: the stored listing_url is exactly the request URL, so we
        # can short-circuit before spending an external API call.
        existing = await self.underwriting_reader.get_by_listing_url(url)
        if existing is not None:
            logger.info(
                "iron_bank.create_underwriting_from_url.already_exists",
                url=url,
                underwriting_id=existing.id,
            )
            raise UnderwritingAlreadyExistsError(existing.id)

        # Same idea one step further: if the listing is already on file under
        # this URL, its market can be checked before the fetch spends an
        # external call and tells upstream to attribute the scrape to a market
        # the listing does not belong to.
        await self._guard_listing_market_by_url(url=url, market_id=market_id)

        zillow_property = await self.zillow_property_service.fetch_property_details(
            url=url, market_id=market_id
        )
        if zillow_property is None:
            logger.warning(
                "iron_bank.create_underwriting_from_url.fetch_failed",
                url=url,
            )
            raise ValueError(
                "Could not fetch Zillow property details for the given URL"
            )

        zpid, listing = await self._resolve_scraped_listing(url, zillow_property)
        await self._guard_listing_market(
            market_id=market_id, listing=listing, zpid=zpid
        )

        market_context = await self._build_market_context(market_id, zillow_property)
        payload = self.builder.build_from_zillow_property(
            listing_url=url,
            zillow_property=zillow_property,
            market_context=market_context,
            current_user_id=current_user_id,
            zpid=zpid,
        )
        return await self.save_service.save(payload)

    async def _resolve_scraped_listing(
        self, url: str, zillow_property: dict[str, Any]
    ) -> tuple[str | None, Any | None]:
        """The zpid to stamp on the row, plus the listing it was resolved from.

        The listing comes back alongside the zpid so the market guard can read
        its preset without a second query — ``get_by_zpid`` already joinedloads
        the preset. ``(None, None)`` when no listings service is wired.

        Fetching details also persists the listing to
        ``zillow.scheduled_listings`` upstream, so this both verifies the scrape
        completed and makes the zpid FK satisfiable. A missing row is treated as
        a failed scrape rather than as "create it without a zpid": a detached
        deal is invisible to every job that keys on zpid (price reconciliation,
        property_pending sync, the automated duplicate guard), and it silently
        opens a second series for a property that already has one.
        """
        if self.listings_service is None:
            return None, None

        zpid = zillow_property.get("id")
        zpid = str(zpid) if zpid is not None else None
        if zpid is None:
            logger.warning(
                "iron_bank.create_underwriting_from_url.no_zpid_in_property",
                url=url,
            )
            raise ListingNotScrapedError(url, None)

        listing = await self.listings_service.get_by_zpid(zpid)
        if listing is None:
            logger.warning(
                "iron_bank.create_underwriting_from_url.listing_not_scraped",
                url=url,
                zpid=zpid,
                detail="property details fetched but no scheduled_listings row",
            )
            raise ListingNotScrapedError(url, zpid)

        logger.info(
            "iron_bank.create_underwriting_from_url.listing_resolved",
            url=url,
            zpid=zpid,
        )
        return zpid, listing

    async def _guard_listing_market_by_url(
        self, *, url: str, market_id: int | None
    ) -> None:
        """The market guard, run before the fetch when the URL is on file.

        Best effort by design: ``detail_url`` is written by the upstream
        scraper, so an analyst's pasted URL only matches it verbatim some of the
        time (query strings, trailing slashes, shortened links). A miss here is
        not "no conflict" — it just means the conflict can't be seen yet, and
        the post-fetch guard on the zpid remains the authoritative one. What
        this buys is skipping the external call, and the wrong-market scrape
        attribution that comes with it, whenever the URL does match.
        """
        if self.listings_service is None:
            return

        listing = await self.listings_service.get_by_detail_url(url)
        if listing is None:
            logger.debug(
                "iron_bank.create_underwriting_from_url.url_not_on_file",
                url=url,
                detail="pre-fetch market guard skipped — falling through to zpid",
            )
            return

        await self._guard_listing_market(
            market_id=market_id,
            listing=listing,
            zpid=getattr(listing, "zpid", None),
        )

    async def _guard_listing_market(
        self,
        *,
        market_id: int | None,
        listing: Any | None,
        zpid: str | None,
    ) -> None:
        """Reject a request whose market contradicts the listing's own.

        Runs even when the analyst sent no ``market_id``: a listing sitting in a
        real market's preset has a right answer to offer, and defaulting to the
        zeroed template instead would seed the deal with no opex at all.

        Keyed on the preset's ``market_id``, not on ``is_default`` — a listing in
        a market's secondary preset still belongs to that market. A NULL
        ``market_id`` is the exploratory bucket: the listing genuinely has no
        market yet, there is no correct id to send back, and blocking would stop
        an analyst from promoting an exploratory find into a market. So it
        passes.
        """
        if listing is None:
            return

        # preset_id is NOT NULL upstream and get_by_zpid joinedloads it, so this
        # is only ever absent if the mirror model drifts or a caller passes a
        # thinner row. Skip rather than 500 on a create path.
        preset = getattr(listing, "preset", None)
        if preset is None:
            logger.warning(
                "iron_bank.create_underwriting_from_url.listing_preset_missing",
                zpid=zpid,
                detail="market guard skipped — no preset on the listing row",
            )
            return

        listing_market_id = preset.market_id
        if listing_market_id is None or listing_market_id == market_id:
            return

        # Resolved only on the way out: an id means nothing to the analyst
        # picking a market, but naming it costs a query, so the happy path
        # never pays for it.
        listing_market_name = await self._resolve_market_name(listing_market_id)

        logger.info(
            "iron_bank.create_underwriting_from_url.market_mismatch",
            zpid=zpid,
            requested_market_id=market_id,
            listing_market_id=listing_market_id,
            listing_market_name=listing_market_name,
        )
        raise ListingMarketMismatchError(
            requested_market_id=market_id,
            listing_market_id=listing_market_id,
            listing_market_name=listing_market_name,
            zpid=zpid,
        )

    async def _resolve_market_name(self, market_id: int) -> str | None:
        """Name the market for the error, or None if it can't be named.

        Never fails the guard: the conflict is real whether or not we can put a
        name to it, so a lookup problem degrades the message to the id rather
        than replacing a 409 the client can act on with a 500 it can't.
        """
        if self.market_name_reader is None:
            return None
        try:
            return await self.market_name_reader.get_market_name_current(market_id)
        except Exception as e:
            logger.warning(
                "iron_bank.create_underwriting_from_url.market_name_lookup_failed",
                market_id=market_id,
                error=str(e),
            )
            return None

    async def _build_market_context(
        self, market_id: int | None, zillow_property: dict[str, Any]
    ) -> MarketContext | None:
        """Load the market context keyed to the fetched property's size.

        The opex rows are keyed by bedrooms and sqft, both of which come off the
        live fetch. Returns ``None`` when no reader is configured, in which case
        the payload falls back to defaults with no line items.
        """
        if self.market_context_reader is None:
            logger.warning(
                "iron_bank.create_underwriting_from_url.no_market_context_reader",
                market_id=market_id,
                detail="opex and rehab line items will not be seeded",
            )
            return None

        context = await self.market_context_reader.build_market_context(
            market_id=market_id,
            # Zillow reports bedrooms as a number that may arrive as a float,
            # unlike scheduled_listings.beds; the opex lookup keys on an int.
            bedrooms=self._as_int(zillow_property.get("bedrooms")),
            area=self._as_int(zillow_property.get("area")),
        )
        logger.info(
            "iron_bank.create_underwriting_from_url.market_context_loaded",
            requested_market_id=market_id,
            resolved_market_id=context.market_id,
            is_template=context.market_id is None,
            opex_row_count=len(context.opex.absolute),
        )
        return context

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
