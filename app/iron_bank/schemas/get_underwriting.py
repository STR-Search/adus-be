from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_serializer,
    model_validator,
)

from app.core.reference_data.schemas import ReferenceDataOption
from app.core.serialization import PlainDecimal
from app.iron_bank.enums import (
    DealStatus,
    OpexKeyedOn,
    SortOrder,
    UnderwritingSortBy,
    UnderwritingSource,
)
from app.iron_bank.schemas.underwriting import (
    SINGLE_SELECT_TAG_FIELDS,
    UnderwritingRead,
)

_SQFT_PER_ACRE = Decimal("43560")


class ZillowProperty(BaseModel):
    id: str | None = None
    url: str | None = None
    thumbnail: str | None = None
    price: Decimal | None = None
    address: str | None = None
    bedrooms: int | None = None
    bathrooms: Decimal | None = None
    area: int | None = None
    original_photos: list | None = None
    lot_size_sqft: Decimal | None = None
    description: str | None = None

    @computed_field
    @property
    def lot_size_acres(self) -> Decimal | None:
        """``lot_size_sqft`` expressed in acres (2 dp), for every read path.

        Derived rather than stored so the list, detail, and n8n webhook
        payloads all carry it without any caller doing the conversion.
        """
        if self.lot_size_sqft is None:
            return None
        return (self.lot_size_sqft / _SQFT_PER_ACRE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class GetUnderwritingDetails(BaseModel):
    # from_attributes on the child schemas lets callers validate the ORM rows
    # directly instead of hand-mapping every column to a dict first.
    model_config = ConfigDict(from_attributes=True)

    purchase_details: dict[str, Any] | None = None
    y1_coc_incl_tax_savings: dict[str, Any] | None = None
    forecasted_revenue: dict[str, Any] | None = None
    cleaning_cost: dict[str, Any] | None = None
    property_taxes: dict[str, Any] | None = None
    zillow_property: ZillowProperty | None = None
    analyst_notes: str | None = None
    construction_and_design_notes: str | None = None


class GetUnderwritingTaxes(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    land_assumptions_pct: Decimal | None = None
    sla_multiplier_pct: Decimal | None = None
    improvement_basis: Decimal | None = None
    estimated_short_life_assets: Decimal | None = None
    bonus_amount_pct: Decimal | None = None
    tax_rate_pct: Decimal | None = None
    y1_loss_from_depreciation: Decimal | None = None
    tax_savings: Decimal | None = None


class GetUnderwritingOptimizationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    category: str | None = None
    total_price: Decimal | None = None
    metric: str | None = None
    base_price: Decimal | None = None
    spec: str | None = None
    tier: str | None = None
    notes: str | None = None


class GetUnderwritingOperatingExpense(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: int | None = None
    expense_name: str | None = Field(default=None, alias="expense")
    monthly_amount: Decimal | None = Field(default=None, alias="monthly")


class GetUnderwritingCompSet(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    listing_url: str | None = None
    revenue: Decimal | None = None
    bedrooms: int | None = None
    sleeps: int | None = None
    is_favourite: bool = False


class UserRef(BaseModel):
    """Lightweight users.users reference used to resolve analyst/approver/owner ids."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class UnderwritingRealtorDetail(BaseModel):
    """A markets.realtors row associated with the underwriting's market."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    brokerage: str | None = None


class GetUnderwritingResult(UnderwritingRead):
    # Only populated in simulation mode (interest_rate / down_payment_pct
    # overrides): True when the row's metrics were recalculated, False when the
    # row lacked the inputs to simulate (stored values shown instead). Stays
    # None — and out of the payload — on the normal list path.
    simulated: bool | None = None
    # Resolved users.users references for analyst_id/approver_id/owner_id, and
    # the realtors associated with the underwriting's market (via
    # market_keys_master.realtor_ids). Populated by the read service.
    analyst: UserRef | None = None
    approver: UserRef | None = None
    owner: UserRef | None = None
    realtor_details: list[UnderwritingRealtorDetail] = Field(default_factory=list)
    details: GetUnderwritingDetails | None = None
    taxes: GetUnderwritingTaxes | None = None
    optimization_list: list[GetUnderwritingOptimizationItem] = Field(
        default_factory=list
    )
    operating_expenses: list[GetUnderwritingOperatingExpense] = Field(
        default_factory=list
    )
    comp_set: list[GetUnderwritingCompSet] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _drop_null_simulated(self, handler):
        # Keep the non-simulation response contract unchanged: the `simulated`
        # key only appears when the row went through simulation mode.
        data = handler(self)
        if isinstance(data, dict) and data.get("simulated") is None:
            data.pop("simulated", None)
        return data


class SimulationParams(BaseModel):
    """Echo of the financing overrides a simulated list was computed with."""

    interest_rate: Decimal | None = None
    down_payment_pct: Decimal | None = None


class GetUnderwritingsQuery(BaseModel):
    """Query params for the underwritings list endpoint.

    Field names, types, and defaults mirror the previous inline ``Query(...)``
    params exactly, so the URL contract is unchanged -- the one exception being
    ``market_ids``, which is aliased back to the original ``market_id`` param
    name. The added value is the cross-field ``min <= max`` validation that
    inline params can't express.
    """

    model_config = ConfigDict(populate_by_name=True)

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=20)
    zpid: str | None = None
    bedrooms: int | None = Field(None, ge=0)
    market_ids: list[int] | None = Field(None, alias="market_id")
    deal_status: DealStatus | None = None
    analyst_id: int | None = None
    owner_id: int | None = None
    source: UnderwritingSource | None = None
    # free-text match on address/city/state; numeric terms also match sheet_number
    search: str | None = Field(None, max_length=100)
    min_purchase_price: Decimal | None = Field(None, ge=0)
    max_purchase_price: Decimal | None = Field(None, ge=0)
    min_total_oop: Decimal | None = Field(None, ge=0)
    max_total_oop: Decimal | None = Field(None, ge=0)
    min_l_cash_on_cash: Decimal | None = None
    max_l_cash_on_cash: Decimal | None = None
    min_m_cash_on_cash: Decimal | None = None
    max_m_cash_on_cash: Decimal | None = None
    min_h_cash_on_cash: Decimal | None = None
    max_h_cash_on_cash: Decimal | None = None
    min_prr: Decimal | None = Field(None, ge=0)
    max_prr: Decimal | None = Field(None, ge=0)
    # Calendar dates (YYYY-MM-DD), both ends inclusive: min == max selects that
    # single day. Bounds are interpreted in UTC against the stored timestamps.
    min_created_at: date | None = None
    max_created_at: date | None = None
    min_deal_approved: date | None = None
    max_deal_approved: date | None = None
    # Boolean deal tags. Omit a tag to ignore it; ``true`` returns only flagged
    # deals, ``false`` only unflagged ones. Because these columns are nullable
    # with a Python-side default, "unflagged" covers both false and NULL — see
    # ``_boolean_tag_conditions`` in the repository. Multiple tags AND together.
    turnkey: bool | None = None
    furnished: bool | None = None
    luxury: bool | None = None
    tax_efficient: bool | None = None
    new_construction: bool | None = None
    existing_airbnb: bool | None = None
    arv: bool | None = None
    high_cash_on_cash: bool | None = None
    low_cash_on_cash: bool | None = None
    add_inground_pool: bool | None = None
    waterfront: bool | None = None
    remote: bool | None = None
    can_support_cohost: bool | None = None
    # Single-select deal tags. Values are reference-data *keys* (the slug stored
    # on the column), not labels — the frontend already gets them from
    # ``GET /reference-data``. Accepts repeated or comma-separated params, so a
    # filter UI can offer several choices for one tag: values within a tag OR
    # together, different tags AND together. Keys are only unique within their
    # own set (``low``/``high`` exist in three sets), which is why each tag has
    # its own param rather than one shared one.
    execution_type: list[str] | None = None
    regulatory_clarity: list[str] | None = None
    offer_competitiveness: list[str] | None = None
    cash_flow_quality: list[str] | None = None
    view_quality: list[str] | None = None
    pool_type: list[str] | None = None
    primary_guest_avatar: list[str] | None = None
    sort_by: UnderwritingSortBy = UnderwritingSortBy.ID
    sort_order: SortOrder = SortOrder.DESC
    # Simulation mode: when either override is present, list metrics are
    # recalculated with it (nothing is persisted) and filtering/sorting run on
    # the simulated values. Fractional values, e.g. 0.069 and 0.1.
    interest_rate: Decimal | None = Field(None, ge=0, lt=1)
    down_payment_pct: Decimal | None = Field(None, ge=0, le=1)

    @field_validator("market_ids", mode="before")
    @classmethod
    def split_market_ids(cls, value):
        """Flatten comma-separated values and normalize "no filter" to None.

        An empty result becomes None rather than [] so the repository never has
        to reason about an ``IN ()`` that would match nothing.
        """
        if value is None:
            return None
        values = value if isinstance(value, list) else [value]
        flattened = []
        for item in values:
            if isinstance(item, str):
                flattened.extend(part.strip() for part in item.split(","))
            else:
                flattened.append(item)
        cleaned = [item for item in flattened if item != "" and item is not None]
        return cleaned or None

    @field_validator(*SINGLE_SELECT_TAG_FIELDS, mode="before")
    @classmethod
    def split_single_select_tags(cls, value):
        """Flatten repeated/comma-separated tag keys; "no filter" becomes None.

        Only blank entries are dropped. Note ``pool_type=none`` is a real key
        meaning "no pool", so a value is never interpreted as absence — that
        distinction is exactly why the empty check is ``== ""`` and not falsy.
        """
        if value is None:
            return None
        values = value if isinstance(value, list) else [value]
        flattened = []
        for item in values:
            if isinstance(item, str):
                flattened.extend(part.strip() for part in item.split(","))
            else:
                flattened.append(item)
        cleaned = [item for item in flattened if item != "" and item is not None]
        return cleaned or None

    @model_validator(mode="after")
    def check_ranges(self):
        if (
            self.min_purchase_price is not None
            and self.max_purchase_price is not None
            and self.min_purchase_price > self.max_purchase_price
        ):
            raise ValueError(
                "min_purchase_price must be less than or equal to max_purchase_price"
            )
        if (
            self.min_total_oop is not None
            and self.max_total_oop is not None
            and self.min_total_oop > self.max_total_oop
        ):
            raise ValueError(
                "min_total_oop must be less than or equal to max_total_oop"
            )
        if (
            self.min_l_cash_on_cash is not None
            and self.max_l_cash_on_cash is not None
            and self.min_l_cash_on_cash > self.max_l_cash_on_cash
        ):
            raise ValueError(
                "min_l_cash_on_cash must be less than or equal to max_l_cash_on_cash"
            )
        if (
            self.min_m_cash_on_cash is not None
            and self.max_m_cash_on_cash is not None
            and self.min_m_cash_on_cash > self.max_m_cash_on_cash
        ):
            raise ValueError(
                "min_m_cash_on_cash must be less than or equal to max_m_cash_on_cash"
            )
        if (
            self.min_h_cash_on_cash is not None
            and self.max_h_cash_on_cash is not None
            and self.min_h_cash_on_cash > self.max_h_cash_on_cash
        ):
            raise ValueError(
                "min_h_cash_on_cash must be less than or equal to max_h_cash_on_cash"
            )
        if (
            self.min_prr is not None
            and self.max_prr is not None
            and self.min_prr > self.max_prr
        ):
            raise ValueError("min_prr must be less than or equal to max_prr")
        if (
            self.min_created_at is not None
            and self.max_created_at is not None
            and self.min_created_at > self.max_created_at
        ):
            raise ValueError(
                "min_created_at must be less than or equal to max_created_at"
            )
        if (
            self.min_deal_approved is not None
            and self.max_deal_approved is not None
            and self.min_deal_approved > self.max_deal_approved
        ):
            raise ValueError(
                "min_deal_approved must be less than or equal to max_deal_approved"
            )
        return self


class GetUnderwritingsResult(BaseModel):
    data: list[GetUnderwritingResult]
    total: int
    page: int
    page_size: int
    pages: int
    # Present only in simulation mode; echoes the overrides applied.
    simulation: SimulationParams | None = None

    @model_serializer(mode="wrap")
    def _drop_null_simulation(self, handler):
        data = handler(self)
        if isinstance(data, dict) and data.get("simulation") is None:
            data.pop("simulation", None)
        return data


class ConstructionAmenityOption(BaseModel):
    id: int
    location: str | None = None
    amenity_name: str | None = None
    price_tier_1: PlainDecimal | None = None
    price_tier_2: PlainDecimal | None = None
    price_tier_3: PlainDecimal | None = None
    notes: str | None = None


class ConstructionRemodelingOption(BaseModel):
    id: int
    location: str | None = None
    rehab_item: str | None = None
    metric: str | None = None
    price_tier_1: PlainDecimal | None = None
    price_tier_2: PlainDecimal | None = None
    price_tier_3: PlainDecimal | None = None
    notes: str | None = None


class StoredZillowProperty(ZillowProperty):
    """Persisted shape for non-automated underwritings.

    A permissive superset of ``ZillowProperty``: extra fields are tolerated so
    the stored JSON can grow without breaking validation, while the response
    contract stays the ``ZillowProperty`` subset.
    """

    model_config = ConfigDict(extra="allow")


class OpexOptionInputs(BaseModel):
    """The drivers behind a row whose amount is not a single market figure.

    One flat bag rather than three differently-shaped sub-objects, so a client
    parses one type and reads the keys its row uses. Every key is present when
    ``OpexOption.inputs`` is non-null; the irrelevant ones are null.
    """

    # cleaning: monthly_amount is cost_per_clean x turns_per_month
    cost_per_clean: PlainDecimal | None = None
    turns_per_month: PlainDecimal | None = None
    # pool/hot tub: a range, of which the low end seeds the row
    low: PlainDecimal | None = None
    high: PlainDecimal | None = None
    # property taxes: an annual rate applied to purchase price
    pct: PlainDecimal | None = None


class OpexOption(BaseModel):
    """One row of the operating-expense catalog for a market/bedrooms/sqft.

    Reference data, in the same spirit as ``ConstructionAmenityOption``: what
    the market says this row costs, *not* what the analyst has on their deal.
    The two legitimately diverge the moment anyone edits a figure — the
    persisted ``uw_operating_expenses`` rows are the analyst's ledger, these are
    the market's truth table.

    Order follows ``opex_catalog.OPEX_ROWS``, which is the seeding order. It is
    **not** the analyst's row order: ``sort_order`` is stamped from payload
    position on save, so a reordered deal renders from its own rows.
    """

    key: str
    expense_name: str
    # None means the market supplies no figure for this row — distinct from a
    # market figure that is genuinely zero.
    monthly_amount: PlainDecimal | None = None
    keyed_on: OpexKeyedOn
    # Null for the rows that are a single amount with nothing behind them.
    inputs: OpexOptionInputs | None = None


class EditContextualData(BaseModel):
    construction_amenities: list[ConstructionAmenityOption] = Field(
        default_factory=list
    )
    construction_remodeling: list[ConstructionRemodelingOption] = Field(
        default_factory=list
    )
    # iron_bank domain reference data, grouped by set_code — the same payload
    # served by GET /reference-data?domain=iron_bank.
    deal_tag_options: dict[str, list[ReferenceDataOption]] = Field(default_factory=dict)
    # The market's operating-expense figures for this deal's bedrooms and sqft.
    # Empty for a market-less deal, or one whose market has no row at its
    # bedroom count — there is no truth table to show, and a blank catalog is
    # honest about that.
    opex_options: list[OpexOption] = Field(default_factory=list)


class DealTagOptionsResult(BaseModel):
    # Same payload as EditContextualData.deal_tag_options, served standalone.
    deal_tag_options: dict[str, list[ReferenceDataOption]] = Field(default_factory=dict)


class EditContextData(BaseModel):
    underwriting: GetUnderwritingResult
    contextual: EditContextualData


class GetUnderwritingEditContextResult(BaseModel):
    data: EditContextData
