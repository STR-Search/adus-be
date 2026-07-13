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


class UnderwritingSortBy(StrEnum):
    ID = "id"
    PURCHASE_PRICE = "purchase_price"
    TOTAL_OOP = "total_oop"
    L_CASH_ON_CASH = "l_cash_on_cash"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"
