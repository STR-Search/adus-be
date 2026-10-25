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


# ── Transaction control (process log needs status + log row in one commit) ──


class SessionCalls(CapturingDb):
    """Records commit/flush/rollback/refresh calls in order."""

    def __init__(self, result_value=None, fail_on=None):
        super().__init__(result_value)
        self.calls: list[str] = []
        self.added: list = []
        self.fail_on = fail_on

    def add(self, instance):
        self.added.append(instance)

    async def _call(self, name):
        self.calls.append(name)
        if name == self.fail_on:
            raise RuntimeError(f"{name} failed")

    async def flush(self):
        await self._call("flush")

    async def commit(self):
        await self._call("commit")

    async def rollback(self):
        await self._call("rollback")

    async def refresh(self, instance):
        await self._call("refresh")


def postgres_sql(query) -> str:
    from sqlalchemy.dialects import postgresql

    return " ".join(str(query.compile(dialect=postgresql.dialect())).split())


@pytest.mark.asyncio
async def test_get_by_id_does_not_lock_by_default():
    db = CapturingDb()
    await UnderwritingRepository(db).get_by_id(7)
    assert "FOR UPDATE" not in postgres_sql(db.query)


@pytest.mark.asyncio
async def test_get_by_id_for_update_locks_only_the_underwriting_row():
    db = CapturingDb()
    await UnderwritingRepository(db).get_by_id(7, for_update=True)
    # OF keeps the lock off the tables in the select list's aggregate subqueries.
    assert postgres_sql(db.query).endswith("FOR UPDATE OF underwritings")
    # Re-read from the DB even if the session holds a stale copy.
    assert db.query.get_execution_options()["populate_existing"] is True


@pytest.mark.asyncio
async def test_create_commits_by_default():
    db = SessionCalls()
    await UnderwritingRepository(db).create({"deal_status": "template_generated"})
    assert db.calls == ["flush", "commit", "refresh"]


@pytest.mark.asyncio
async def test_create_without_commit_only_flushes():
    db = SessionCalls()
    await UnderwritingRepository(db).create(
        {"deal_status": "template_generated"}, commit=False
    )
    assert "commit" not in db.calls
    assert db.calls == ["flush", "flush", "refresh"]


@pytest.mark.asyncio
async def test_create_without_commit_rolls_back_on_error():
    db = SessionCalls(fail_on="refresh")
    with pytest.raises(RuntimeError):
        await UnderwritingRepository(db).create({}, commit=False)
    assert db.calls[-1] == "rollback"


@pytest.mark.asyncio
async def test_update_without_commit_only_flushes():
    from app.iron_bank.models.underwriting import Underwriting

    db = SessionCalls(result_value=Underwriting(id=7, deal_status="maybe"))
    updated = await UnderwritingRepository(db).update(
        7, {"deal_status": "analyst_started"}, commit=False
    )
    assert updated.deal_status == "analyst_started"
    assert db.calls == ["flush", "refresh"]


@pytest.mark.asyncio
async def test_update_commits_by_default():
    from app.iron_bank.models.underwriting import Underwriting

    db = SessionCalls(result_value=Underwriting(id=7, deal_status="maybe"))
    await UnderwritingRepository(db).update(7, {"deal_status": "analyst_started"})
    assert db.calls == ["commit", "refresh"]


@pytest.mark.asyncio
async def test_commit_rolls_back_on_failure():
    db = SessionCalls(fail_on="commit")
    with pytest.raises(RuntimeError):
        await UnderwritingRepository(db).commit()
    assert db.calls == ["commit", "rollback"]
