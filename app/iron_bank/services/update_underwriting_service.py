from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder

from app.core.logger import logger
from app.iron_bank.enums import DealStatus
from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository
from app.iron_bank.schemas.deal_status import UpdateDealStatusResult
from app.iron_bank.schemas.save_underwriting import SaveUnderwritingPayload
from app.iron_bank.schemas.underwriting import UnderwritingRead
from app.iron_bank.schemas.update_underwriting import (
    UpdateUnderwritingPayload,
    UpdateUnderwritingResult,
)
from app.iron_bank.services.save_underwriting_service import SaveUnderwritingService
from app.iron_bank.services.underwriting_calculator import UnderwritingCalculator


class UpdateUnderwritingService(SaveUnderwritingService):
    _PRICE_RECONCILIATION_FIELDS = {
        "purchase_price",
        "total_oop",
        "prr",
        "budget_to_pp",
        "l_cash_on_cash",
        "m_cash_on_cash",
        "h_cash_on_cash",
    }

    def __init__(
        self,
        repository: UnderwritingRepository,
        calculator: UnderwritingCalculator | None = None,
        market_service=None,
        listings_service=None,
        cleaned_data_service=None,
        reference_data_service=None,
        n8n_webhook_service=None,
    ):
        super().__init__(
            repository=repository,
            calculator=calculator,
            market_service=market_service,
            listings_service=listings_service,
            cleaned_data_service=cleaned_data_service,
            reference_data_service=reference_data_service,
        )
        # Optional by design: only the HTTP deal-status path wires this in, so
        # machine-driven flows (e.g. ReconcileUnderwritingPriceJob) can never
        # fire a client-facing automation.
        self.n8n_webhook_service = n8n_webhook_service

    async def update(
        self,
        underwriting_id: int,
        payload: UpdateUnderwritingPayload,
    ) -> UpdateUnderwritingResult:
        data = payload.model_dump(exclude_unset=True)

        underwriting_data = {
            key: value for key, value in data.items() if key not in self._CHILD_FIELDS
        }
        await self._validate_reference_data_fields(underwriting_data)
        tax_data = self._build_tax_data(payload) if "taxes" in data else None
        detail_data = None
        if "details" in data:
            market_id, bedrooms = await self._resolve_market_and_bedrooms_for_update(
                underwriting_id, payload
            )
            detail_data = await self._build_detail_data(
                payload, tax_data, market_id=market_id, bedrooms=bedrooms
            )
        self._apply_calculated_underwriting_fields(
            underwriting_data,
            detail_data,
            payload.optimization_list,
        )

        underwriting = await self.repository.update(
            underwriting_id=underwriting_id,
            underwriting_data=underwriting_data,
            detail_data=jsonable_encoder(detail_data) if detail_data else None,
            tax_data=tax_data,
            optimization_items=(
                [
                    item.model_dump(exclude_unset=True)
                    for item in payload.optimization_list
                ]
                if "optimization_list" in data
                else None
            ),
            operating_expenses=(
                [
                    item.model_dump(exclude_unset=True)
                    for item in payload.operating_expenses
                ]
                if "operating_expenses" in data
                else None
            ),
            comp_set=(
                [item.model_dump(exclude_unset=True) for item in payload.comp_set]
                if "comp_set" in data
                else None
            ),
        )
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        return UpdateUnderwritingResult(underwriting_id=underwriting.id)

    async def _resolve_market_and_bedrooms_for_update(
        self,
        underwriting_id: int,
        payload: UpdateUnderwritingPayload,
    ) -> tuple[int | None, int | None]:
        """Recover the inputs the Airbnb revenue estimate needs.

        ``market_id`` may be (re)assigned in the update payload; the property
        data (bedrooms) lives on the persisted row, since the update payload
        usually doesn't resend it. We only fetch the existing record when an
        estimate could actually be produced — i.e. the update sets
        ``purchase_details`` but no explicit ``forecasted_revenue`` — so
        unrelated updates don't pay for a lookup.
        """
        needs_estimate = (
            payload.details is not None
            and payload.details.purchase_details is not None
            and payload.details.forecasted_revenue is None
        )
        if not needs_estimate:
            return None, None

        existing = await self.repository.get_by_id(underwriting_id)
        if existing is None:
            return payload.market_id, None

        market_id = (
            payload.market_id if payload.market_id is not None else existing.market_id
        )
        bedrooms = await self._resolve_bedrooms_for_update(payload, existing)
        return market_id, bedrooms

    async def _resolve_bedrooms_for_update(
        self,
        payload: UpdateUnderwritingPayload,
        existing,
    ) -> int | None:
        """Resolve bedrooms for the revenue estimate on update.

        Prefers a ``zillow_property`` resent in the update payload, then the
        stored ``zillow_property`` on the existing row (non-automated), then
        ``scheduled_listings`` via the row's ``zpid`` (automated).
        """
        if (
            payload.details is not None
            and payload.details.zillow_property is not None
            and payload.details.zillow_property.bedrooms is not None
        ):
            return payload.details.zillow_property.bedrooms

        stored = (
            getattr(existing.detail, "zillow_property", None)
            if existing.detail
            else None
        )
        if isinstance(stored, dict) and stored.get("bedrooms") is not None:
            return stored["bedrooms"]

        if self.listings_service is not None and existing.zpid is not None:
            listing = await self.listings_service.get_by_zpid(existing.zpid)
            if listing is not None:
                return listing.beds

        return None

    async def update_deal_status(
        self,
        *,
        underwriting_id: int,
        deal_status: DealStatus,
        actor_user_id: int,
    ) -> UpdateDealStatusResult:
        existing = await self.repository.get_by_id(underwriting_id)
        if existing is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        # Bind before repository.update: that call re-fetches through
        # SQLAlchemy's identity map and mutates this same object, so reading
        # existing.deal_status afterwards would return the NEW status.
        previous_status = existing.deal_status

        underwriting_data: dict = {"deal_status": deal_status}
        # Assign the analyst on first touch only; never overwrite an existing one.
        if existing.analyst_id is None:
            underwriting_data["analyst_id"] = actor_user_id
        # The approver is whoever moves the deal to "present to clients".
        if deal_status == DealStatus.PRESENT_TO_CLIENTS:
            underwriting_data["approver_id"] = actor_user_id
            underwriting_data["deal_approved"] = datetime.now(timezone.utc)

        # Before repository.update so its commit covers both writes atomically.
        await self._sync_listing_removal(existing, deal_status)

        underwriting = await self.repository.update(
            underwriting_id=underwriting_id,
            underwriting_data=underwriting_data,
        )
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")

        # Only now is the row committed — safe to announce it externally. The
        # previous-status check stops a repeated PATCH (double-click, client
        # retry) from notifying clients twice about the same deal.
        if (
            deal_status == DealStatus.PRESENT_TO_CLIENTS
            and previous_status != DealStatus.PRESENT_TO_CLIENTS
        ):
            await self._trigger_n8n_webhook(underwriting)

        return UpdateDealStatusResult(
            underwriting_id=underwriting.id,
            deal_status=underwriting.deal_status,
        )

    async def _trigger_n8n_webhook(self, underwriting) -> None:
        """POST the underwriting row to the n8n automation webhook.

        Never raises. The status write has already committed, so an n8n outage
        must not surface to the caller — it cannot be allowed to 500 an
        approver's status change.

        The body is the parent ``underwritings`` row only, serialized through
        ``UnderwritingRead`` — the same shape ``GetUnderwritingService`` returns
        for the parent, so n8n sees a field set it can also fetch from
        ``GET /iron-bank/underwritings/{id}``. Child tables (details, taxes,
        opex, comps) are deliberately excluded; n8n can call back for those.
        """
        if self.n8n_webhook_service is None:
            return

        # Field-by-field getattr (rather than validating the ORM object
        # directly) never touches a relationship attribute, which would raise
        # MissingGreenlet under async SQLAlchemy. Nones are dropped so the
        # schema's own defaults apply: UnderwritingRead declares the tag
        # booleans as non-optional (`turnkey: bool = False`), and a nullable
        # column that happens to be NULL would otherwise fail validation.
        row = UnderwritingRead.model_validate(
            {
                field: value
                for field in UnderwritingRead.model_fields
                if (value := getattr(underwriting, field, None)) is not None
            }
        )

        try:
            # mode="json" keeps Decimal as a string ("525000.00") rather than
            # coercing to float the way jsonable_encoder would.
            await self.n8n_webhook_service.send(payload=row.model_dump(mode="json"))
        except Exception:
            logger.exception(
                "iron_bank.deal_status.webhook_failed",
                underwriting_id=underwriting.id,
            )

    async def _sync_listing_removal(self, existing, deal_status: DealStatus) -> None:
        """Mirror the delete_zillow status onto the linked scheduled listing.

        Entering delete_zillow flags the listing for removal; leaving it
        clears the flag. Skips silently when there is no linked listing.
        """
        if self.listings_service is None or existing.zpid is None:
            return
        if deal_status == DealStatus.DELETE_ZILLOW:
            remove = True
        elif existing.deal_status == DealStatus.DELETE_ZILLOW:
            remove = False
        else:
            return
        await self.listings_service.set_remove_listing(existing.zpid, remove)

    async def reconcile_purchase_price(
        self,
        underwriting_id: int,
        payload: SaveUnderwritingPayload,
    ) -> UpdateUnderwritingResult:
        tax_data = self._build_tax_data(payload)
        bedrooms = await self._resolve_bedrooms_for_save(payload)
        detail_data = await self._build_detail_data(
            payload, tax_data, market_id=payload.market_id, bedrooms=bedrooms
        )
        calculated_underwriting_data: dict = {}
        self._apply_calculated_underwriting_fields(
            calculated_underwriting_data,
            detail_data,
            payload.optimization_list,
        )
        underwriting_data = {
            key: value
            for key, value in calculated_underwriting_data.items()
            if key in self._PRICE_RECONCILIATION_FIELDS
        }

        underwriting = await self.repository.update(
            underwriting_id=underwriting_id,
            underwriting_data=underwriting_data,
            detail_data=jsonable_encoder(detail_data) if detail_data else None,
            tax_data=tax_data,
            optimization_items=None,
            operating_expenses=None,
            comp_set=None,
        )
        if underwriting is None:
            raise LookupError(f"Underwriting {underwriting_id} not found")
        return UpdateUnderwritingResult(underwriting_id=underwriting.id)
