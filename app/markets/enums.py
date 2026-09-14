from enum import StrEnum


class MarketStatus(StrEnum):
    """``market_keys_master.market_status`` values.

    Used to validate the market list endpoints' ``market_status`` filter. The
    column itself is free-text varchar, so this constrains what a client may
    filter by rather than what the table can hold — a row seeded with some
    other value (see ``scripts/seeding_scripts/seed_markets.py``, which writes
    the CSV value verbatim) stays reachable through the unfiltered call.
    """

    ACTIVE = "active"
    EXPLORATORY = "exploratory"
