import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.util import greenlet_spawn

from app.core import profiling
from app.core.profiling import (
    ProfilingMiddleware,
    RequestProfile,
    _query_label,
    current_profile,
    timed,
)


def test_timed_is_a_noop_without_a_request_profile():
    with timed("anything"):
        pass
    assert current_profile() is None


def test_nested_spans_record_each_name_but_count_top_level_once():
    profile = RequestProfile(method="GET", path="/x")
    token = profiling._current.set(profile)
    try:
        with timed("outer"):
            with timed("inner"):
                pass
            with timed("inner"):
                pass
    finally:
        profiling._current.reset(token)

    assert set(profile.spans) == {"outer", "inner"}
    assert profile.top_level_ms == profile.spans["outer"]


@pytest.mark.parametrize(
    ("statement", "label"),
    [
        (
            'SELECT count(*) AS count_1 FROM (SELECT iron_bank.underwritings.id '
            'FROM iron_bank.underwritings) AS anon_1',
            "COUNT iron_bank.underwritings",
        ),
        (
            "SELECT iron_bank.uw_comp_set.id\nFROM iron_bank.uw_comp_set WHERE ...",
            "SELECT iron_bank.uw_comp_set",
        ),
        ('UPDATE "users"."api_keys" SET last_used_at=$1', "UPDATE users.api_keys"),
        ("INSERT INTO iron_bank.underwritings (id) VALUES ($1)", "INSERT iron_bank.underwritings"),
    ],
)
def test_query_label(statement, label):
    assert _query_label(statement) == label


@pytest.mark.asyncio
async def test_profile_is_visible_inside_sqlalchemy_greenlet_bridge():
    # The engine hooks run synchronously inside greenlet_spawn; if the request's
    # contextvar didn't carry over, every query would go unrecorded.
    profile = RequestProfile(method="GET", path="/x")
    token = profiling._current.set(profile)
    try:
        seen = await greenlet_spawn(current_profile)
    finally:
        profiling._current.reset(token)
    assert seen is profile


def test_middleware_sets_server_timing_header_with_spans():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        with timed("work"):
            pass
        return {"ok": True}

    app.add_middleware(ProfilingMiddleware)
    response = TestClient(app).get("/ping")

    header = response.headers["server-timing"]
    assert "work;dur=" in header
    assert 'db;dur=0.0;desc="0 queries"' in header
    assert "total;dur=" in header
    assert response.headers["timing-allow-origin"] == "*"
