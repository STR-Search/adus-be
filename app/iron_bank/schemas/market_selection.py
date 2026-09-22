"""Shared handling of an optional ``market_id`` on the create payloads.

Both non-automated create paths let the analyst start a deal without picking a
market, and both receive the same sentinel from the client when they do.
"""


def normalize_absent_market(value: int | None) -> int | None:
    """Treat ``0`` as "no market selected".

    Clients send 0 from an unselected dropdown. There is no market with
    id 0 (``market_keys_master`` starts at 1), so without this the value
    flows through as a real id: the context loads empty and the insert then
    violates the FK to markets.market_keys_master. Folding it to None picks
    up the existing market-less path in
    ``PrepareUwDataJob.build_market_context``, which seeds the full template
    with zeroed amounts.
    """
    return None if value == 0 else value
