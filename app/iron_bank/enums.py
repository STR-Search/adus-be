from enum import StrEnum


class DealStatus(StrEnum):
    TEMPLATE_GENERATED = "template_generated"
    ANALYST_STARTED = "analyst_started"
    ANALYST_COMPLETED = "analyst_completed"
    DELETE_ZILLOW = "delete_zillow"
    DELETE_DEAL = "delete_deal"
    MAYBE = "maybe"
    RE_FORECAST_REVENUE = "re_forecast_revenue"
    AWAITING_REALTOR_DETAILS = "awaiting_realtor_details"
    PRESENT_TO_CLIENTS = "present_to_clients"
    CLIENT_UNDER_CONTRACT = "client_under_contract"
    TRAINING_DEAL = "training_deal"
    PREVIOUSLY_UNDERWRITTEN_NO_STATUS = "previously_underwritten_no_status"


class UnderwritingSource(StrEnum):
    ADUS = "adus"
    LEGACY_SHEET = "legacy_sheet"


class UnderwritingSortBy(StrEnum):
    # Values are ORM attribute names on ``Underwriting`` — the repository and
    # the simulation sorter both resolve them with getattr, so a value that
    # isn't a real column (or isn't carried on ``_SimulatedRow``) breaks at
    # request time, not import time.
    ID = "id"
    PURCHASE_PRICE = "purchase_price"
    TOTAL_OOP = "total_oop"
    L_CASH_ON_CASH = "l_cash_on_cash"
    M_CASH_ON_CASH = "m_cash_on_cash"
    H_CASH_ON_CASH = "h_cash_on_cash"
    SHEET_NUMBER = "sheet_number"
    CREATED_AT = "created_at"
    DEAL_APPROVED = "deal_approved"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class OpexKeyedOn(StrEnum):
    """What an operating-expense row's market figure varies with.

    Tells a client which rows a change to the deal's bedroom count or square
    footage would re-seed: ``BEDROOMS`` rows come from ``opex_by_bedrooms``,
    ``SIZE`` rows from ``opex_by_size``, and ``NONE`` rows have no market source
    at all (they seed from a default and only ever change by hand).

    A property of the row itself, so it is the same answer whether or not this
    market happens to have a row at this deal's bedrooms or sqft.
    """

    BEDROOMS = "bedrooms"
    SIZE = "size"
    NONE = "none"
