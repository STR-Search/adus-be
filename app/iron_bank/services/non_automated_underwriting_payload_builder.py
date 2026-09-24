from decimal import Decimal
from typing import Any

from app.iron_bank.enums import UnderwritingSource
from app.iron_bank.schemas.prepare_uw import MarketContext
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.services import opex_catalog
from app.iron_bank.services.base_underwriting_payload_builder import (
    BaseUnderwritingPayloadBuilder,
)


class NonAutomatedUnderwritingPayloadBuilder(BaseUnderwritingPayloadBuilder):
    """Builds a non-automated save payload, from Zillow data or from nothing.

    Two entry points over one assembly. ``build_from_zillow_property`` serves
    the create-from-URL flow: the external API has already been called and
    mapped to a ``zillow_property`` dict. ``build_blank`` serves the off-market
    flow, where there is no listing and the analyst supplies the price (and
    optionally the market and size) by hand.

    Both share ``_build``. When a ``market_context`` is given the opex and rehab
    line items are seeded from it through the same base-class helpers the
    automated flow uses (a market-less deal gets a zeroed template context — see
    ``PrepareUwDataService.to_template_market_context``); without one, financing
    and tax terms are seeded with defaults and no line items are produced. The
    ``zillow_property`` blob is stored on ``uw_details`` (``is_automated=False``)
    so it is read back from storage rather than hydrated live — on the blank
    path it is a stub carrying only what the analyst typed. Ownership follows
    the market's analyst owner when there is one, otherwise ``current_user_id``.
    Does not fetch data or persist anything.
    """

    def build_from_zillow_property(
        self,
        *,
        listing_url: str,
        zillow_property: dict[str, Any],
        market_context: MarketContext | None = None,
        current_user_id: int | None = None,
        zpid: str | None = None,
    ) -> SaveUnderwritingPayload:
        # street/city/state ride along on the fetched dict but belong on the
        # underwritings row's own columns, not in the stored zillow_property
        # blob — lift them out before the rest is persisted on uw_details.
        zillow_property = dict(zillow_property)
        street = zillow_property.pop("street", None)
        city = zillow_property.pop("city", None)
        state = zillow_property.pop("state", None)

        return self._build(
            zillow_property=zillow_property,
            purchase_price=self._money_to_decimal(zillow_property.get("price")),
            bedrooms=self._as_int(zillow_property.get("bedrooms")),
            bathrooms=zillow_property.get("bathrooms"),
            market_context=market_context,
            current_user_id=current_user_id,
            # No source: this path falls through to the "adus" server default,
            # as it did before the blank path existed.
            source=None,
            # The top-level ``zpid`` column has a FK to
            # ``zillow.scheduled_listings``, so it may only be set once the
            # listing is known to be in that table. Fetching property details
            # now persists the listing upstream, so the caller verifies the row
            # exists and passes the zpid in; callers that don't verify pass
            # nothing and the column stays null, as it did before scraping wrote
            # to scheduled_listings. Either way the zpid is preserved on
            # ``details.zillow_property.id``.
            zpid=zpid,
            listing_url=listing_url,
            property_address=zillow_property.get("address"),
            street=street,
            city=city,
            state=state,
        )

    def build_blank(
        self,
        *,
        purchase_price: Decimal,
        market_context: MarketContext,
        listing_url: str | None = None,
        bedrooms: int | None = None,
        bathrooms: Decimal | None = None,
        current_user_id: int | None = None,
    ) -> SaveUnderwritingPayload:
        """Seed a deal that has no listing behind it.

        The remaining listing-derived columns stay null — there is no zpid and
        no address — and ``source`` is stamped ``blank`` so the frontend knows
        to render the hero editable rather than as a listing summary.

        ``listing_url`` is where the analyst found the deal, if anywhere, and
        is optional: an off-market deal often has no link at all. It is not
        required to be a Zillow URL — that is the whole point of this path — so
        a link to anywhere is stored verbatim.

        ``market_context`` is non-optional here: the caller always builds one
        (a zeroed template when no market was picked), so the opex and
        optimization rows always seed and the sheet is never silently empty.
        """
        return self._build(
            zillow_property=self._blank_zillow_property(
                purchase_price=purchase_price,
                listing_url=listing_url,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
            ),
            purchase_price=purchase_price,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            market_context=market_context,
            current_user_id=current_user_id,
            source=UnderwritingSource.BLANK,
            listing_url=listing_url,
        )

    @staticmethod
    def _blank_zillow_property(
        *,
        purchase_price: Decimal,
        listing_url: str | None,
        bedrooms: int | None,
        bathrooms: Decimal | None,
    ) -> dict[str, Any]:
        """The stub blob a blank deal stores, mirroring the Zillow path's shape.

        Written in full rather than as a partial so the hero has a stable write
        target — and a partial PUT replaces the whole JSONB column anyway, so
        the frontend sends the full object back regardless.

        ``price`` is included because it is mandatory on this path and the
        Zillow path keeps it in the blob too. Bed/bath are written here *and* on
        the columns, and are allowed to diverge afterwards: the blob is the
        property as found, the columns are the property as underwritten. Nothing
        reads the blob back as authoritative once the columns are set, so the
        frontend must read bed/bath from the columns.

        ``url`` is the exception to that divergence: unlike bed/bath it has no
        "as found" versus "as underwritten" reading, so the two copies are
        meant to stay equal. Nothing enforces it — a PUT can move one without
        the other — but a caller changing the link should send both.
        """
        return {
            # No zpid: the top-level column's FK to zillow.scheduled_listings
            # can only be satisfied by a scraped listing, and a blank deal has
            # none — so it stays null here and on the column.
            "id": None,
            # Mirrors the listing_url column, keeping the two in step the way
            # the automated builder does (it sets the column *from* this key).
            "url": listing_url,
            "thumbnail": None,
            "price": purchase_price,
            "address": None,  # the hero fills these three in
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "area": None,
            "original_photos": None,
            "lot_size_sqft": None,
            "description": None,
        }

    def _build(
        self,
        *,
        zillow_property: dict[str, Any],
        purchase_price: Decimal | None,
        bedrooms: int | None,
        bathrooms: Any,
        market_context: MarketContext | None,
        current_user_id: int | None,
        source: UnderwritingSource | None,
        zpid: str | None = None,
        listing_url: str | None = None,
        property_address: str | None = None,
        street: str | None = None,
        city: str | None = None,
        state: str | None = None,
    ) -> SaveUnderwritingPayload:
        context = market_context.model_dump() if market_context else {}
        # No market context means no market-derived terms, so the base defaults
        # apply — the same thing an empty config dict yields.
        config = context.get("config") or {}
        opex = context.get("opex") or {}
        cleaning_cost = opex_catalog.build_cleaning_cost(opex.get("cleaning") or {})
        property_taxes = opex_catalog.build_opex_property_taxes(
            property_tax_pct=opex.get("property_tax_pct"),
            purchase_price=purchase_price,
        )

        details = (
            self._build_details(
                purchase_price=purchase_price,
                config=config,
                cleaning_cost=cleaning_cost,
                property_taxes=property_taxes,
            )
            or {}
        )
        details["zillow_property"] = zillow_property

        payload = {
            "zpid": zpid,
            "deal_status": self._DEFAULT_DEAL_STATUS,
            "is_automated": False,
            "listing_url": listing_url,
            # Null for a template (market-less) deal — see
            # to_template_market_context, which clears the identity fields.
            "market_id": context.get("market_id"),
            # A market-less (template) deal has no analyst owner to inherit, so
            # it falls to the analyst who created it.
            "owner_id": self._resolve_owner_id(
                context, fallback_user_id=current_user_id
            ),
            "property_address": property_address,
            "street": street,
            "city": city,
            "state": state,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "purchase_price": purchase_price,
            "details": details,
            "taxes": self._build_taxes(config) if purchase_price is not None else None,
        }
        # Only when there is one to stamp: the save dumps with
        # exclude_unset, so an explicit None would persist NULL over the
        # column's "adus" server default rather than falling through to it.
        if source is not None:
            payload["source"] = source
        if market_context is not None:
            payload["operating_expenses"] = self._build_operating_expenses(
                opex, property_taxes
            )
            payload["optimization_list"] = self._build_optimization_list(
                context, zpid=zillow_property.get("id")
            )
        return SaveUnderwritingPayload.model_validate(payload)
