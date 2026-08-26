import uuid

import pytest

from app.iron_bank.repositories.underwriting_repository import UnderwritingRepository


class FakeResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class CapturingDb:
    """Records the statement instead of running it, so ordering can be asserted."""

    def __init__(self, result_value=None):
        self.query = None
        self.result_value = result_value

    async def execute(self, query):
        self.query = query
        return FakeResult(self.result_value)

    def compiled_sql(self) -> str:
        return str(self.query.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_get_by_listing_url_returns_the_oldest_match():
    """The 409 from the URL-create path redirects to this id.

    Duplicates copy listing_url verbatim, so every version of a series shares
    it — ascending order is what sends the analyst to version 0 rather than to
    whichever copy was made most recently.
    """
    db = CapturingDb()

    await UnderwritingRepository(db).get_by_listing_url(
        "https://www.zillow.com/homedetails/26110417_zpid/"
    )

    sql = db.compiled_sql()
    assert "ORDER BY iron_bank.underwritings.id ASC" in sql
    assert "DESC" not in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_get_next_version_for_series_starts_at_zero_when_empty():
    db = CapturingDb(result_value=None)

    version = await UnderwritingRepository(db).get_next_version_for_series(
        uuid.uuid4()
    )

    assert version == 0


@pytest.mark.asyncio
async def test_get_next_version_for_series_is_one_past_the_max():
    db = CapturingDb(result_value=4)

    version = await UnderwritingRepository(db).get_next_version_for_series(
        uuid.uuid4()
    )

    assert version == 5


@pytest.mark.asyncio
async def test_get_all_by_zpid_orders_oldest_version_first():
    """Reconciliation walks a series in version order, not DB order."""

    class ScalarsDb(CapturingDb):
        async def execute(self, query):
            self.query = query
            return type(
                "R", (), {"scalars": lambda self: type("S", (), {"all": lambda self: []})()}
            )()

    db = ScalarsDb()

    rows = await UnderwritingRepository(db).get_all_by_zpid("26110417")

    assert rows == []
    sql = db.compiled_sql()
    assert "ORDER BY iron_bank.underwritings.version ASC" in sql
    assert "iron_bank.underwritings.id ASC" in sql
    # no LIMIT: every version must come back, not just the newest
    assert "LIMIT" not in sql
