import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.deal_recommendation.agent.context import PoolOverride, RunContext
from app.deal_recommendation.agent.tools import TOOL_DEFINITIONS, ToolExecutor
from app.iron_bank.services.deal_catalog_service import CatalogDealDetails, PoolResult
from tests.deal_recommendation.factories import make_deal


def _deals():
    return [
        make_deal(1, state="FL", total_oop=Decimal("150000"), tax_savings=Decimal("120000")),
        make_deal(2, state="GA", total_oop=Decimal("220000"), tax_savings=Decimal("90000")),
        make_deal(3, state="FL", total_oop=Decimal("390000"), tax_savings=Decimal("160000")),
        make_deal(4, state="TN", total_oop=Decimal("180000"), tax_savings=Decimal("60000")),
        make_deal(5, state="VA", total_oop=Decimal("240000"), tax_savings=Decimal("70000")),
        # 6 and 7 are the same property; 7 survives dedupe (higher id, no dates).
        make_deal(6, property_address="9 Lake Rd, Blue Ridge, GA 30513"),
        make_deal(7, property_address="9 Lake Road, Blue Ridge, GA"),
        make_deal(8, state="NC", total_oop=Decimal("120000"), tax_savings=Decimal("50000")),
    ]


class FakeCatalog:
    def __init__(self, deals=None, text_hits=None):
        self.deals = deals if deals is not None else _deals()
        self.text_hits = text_hits or set()
        self.pool_calls = []

    async def list_candidate_pool(self, **kwargs):
        self.pool_calls.append(kwargs)
        return PoolResult(deals=list(self.deals), dropped_unrecalculable=3)

    async def text_search(self, ids, query):
        return {i for i in ids if i in self.text_hits}

    async def get_details(self, ids, *, down_payment_pct=None, interest_rate=None):
        by_id = {d.id: d for d in self.deals}
        return [
            CatalogDealDetails(
                deal=by_id[i],
                deal_pitch="pitch",
                note=None,
                analyst_notes="notes",
                construction_and_design_notes=None,
                optimization_items=[],
                comp_amenity_counts={"has_pool": 1},
                listing_url=f"https://example.com/{i}",
                video_walkthrough=None,
                loom_vid=None,
                market_name="Market",
            )
            for i in ids
            if i in by_id
        ]


class FakeProfiles:
    def __init__(self):
        self.profiles = []
        self.recommendations = []

    async def add_profile(self, *, conversation_id, run_id, profile):
        self.profiles.append(profile)
        return len(self.profiles)

    async def add_recommendations(self, *, run_id, conversation_id, items):
        self.recommendations.extend(items)


def _ctx(**overrides):
    events = []

    async def emit(event, data):
        events.append((event, data))

    ctx = RunContext(conversation_id=uuid.uuid4(), run_id=uuid.uuid4(), emit=emit, **overrides)
    return ctx, events


def _search_input(**overrides):
    payload = {
        "financing": None,
        "hard": {"max_oop": 400000},
        "weights": {"tax_savings": 5},
        "state_preference": [],
        "tag_preferences": [],
        "text_query": None,
        "text_mode": "filter",
        "exclude_ids": [],
        "limit": 15,
    }
    payload.update(overrides)
    return payload


def _executor(catalog=None):
    profiles = FakeProfiles()
    return ToolExecutor(catalog or FakeCatalog(), profiles), profiles


def _ids(outcome):
    return [c["id"] for c in outcome.content["candidates"]]


@pytest.mark.asyncio
async def test_search_dedupes_and_reports_stage_counts():
    executor, _ = _executor()
    ctx, _ = _ctx()
    outcome = await executor.execute("search_deals", _search_input(), ctx)
    assert not outcome.is_error
    counts = outcome.content["stage_counts"]
    assert counts["pool"] == 8
    assert counts["after_dedupe"] == 7
    assert counts["dropped_unrecalculable"] == 3
    assert 6 not in _ids(outcome) and 7 in _ids(outcome)
    assert _ids(outcome)[0] == 3  # highest tax savings
    assert ctx.seen_ids == set(_ids(outcome))
    assert ctx.max_candidates_seen == 7
    assert "candidates" in outcome.summary


@pytest.mark.asyncio
async def test_search_applies_hard_filters_and_exclusions_including_already_shown():
    executor, _ = _executor()
    ctx, _ = _ctx(already_shown_ids={1})
    outcome = await executor.execute(
        "search_deals",
        _search_input(
            hard={"max_oop": 250000, "states_exclude": ["va"]},
            exclude_ids=[2],
        ),
        ctx,
    )
    ids = _ids(outcome)
    assert 3 not in ids  # over budget
    assert 5 not in ids  # VA excluded
    assert 2 not in ids and 1 not in ids  # exclude_ids + already shown


@pytest.mark.asyncio
async def test_search_text_filter_vs_boost():
    executor, _ = _executor(FakeCatalog(text_hits={4}))
    ctx, _ = _ctx()
    filtered = await executor.execute(
        "search_deals", _search_input(text_query="pickleball", text_mode="filter"), ctx
    )
    assert _ids(filtered) == [4]
    boosted = await executor.execute(
        "search_deals", _search_input(text_query="pickleball", text_mode="boost"), ctx
    )
    assert len(_ids(boosted)) == 7
    assert next(c for c in boosted.content["candidates"] if c["id"] == 4)["breakdown"]["text_match"] > 0


@pytest.mark.asyncio
async def test_search_with_impossible_budget_returns_empty_candidates_with_counts():
    executor, _ = _executor()
    ctx, _ = _ctx()
    outcome = await executor.execute("search_deals", _search_input(hard={"max_oop": 1000}), ctx)
    assert not outcome.is_error
    assert outcome.content["candidates"] == []
    assert outcome.content["stage_counts"]["after_hard_filters"] == 0


@pytest.mark.asyncio
async def test_search_uses_ctx_financing_when_input_omits_it():
    catalog = FakeCatalog()
    executor, _ = _executor(catalog)
    ctx, _ = _ctx(down_payment_pct=Decimal("0.1"))
    outcome = await executor.execute("search_deals", _search_input(), ctx)
    assert catalog.pool_calls[-1]["down_payment_pct"] == Decimal("0.1")
    assert catalog.pool_calls[-1]["statuses"] == ["present_to_clients"]
    assert catalog.pool_calls[-1]["property_pending"] is False
    assert outcome.content["candidates"][0]["interest_rate_is_stored"] is True


@pytest.mark.asyncio
async def test_pool_override_widens_statuses_and_skips_already_shown_exclusion():
    catalog = FakeCatalog()
    executor, _ = _executor(catalog)
    override = PoolOverride(
        statuses=["present_to_clients", "client_under_contract"],
        approved_from=date(2026, 2, 15),
        approved_to=date(2026, 5, 20),
    )
    ctx, _ = _ctx(already_shown_ids={1}, pool_override=override)
    outcome = await executor.execute("search_deals", _search_input(), ctx)
    call = catalog.pool_calls[-1]
    assert call["statuses"] == ["present_to_clients", "client_under_contract"]
    assert call["property_pending"] is None
    assert call["approved_from"] == date(2026, 2, 15)
    assert 1 in _ids(outcome)


@pytest.mark.asyncio
async def test_update_profile_saves_version_sets_ctx_and_emits():
    executor, profiles = _executor()
    ctx, events = _ctx()
    profile = {
        "client_label": "Rav & Anna",
        "financing": {"down_payment_pct": 0.1, "interest_rate": None, "cohost_fee_pct": 0.12},
        "already_shown_ids": [743],
    }
    outcome = await executor.execute("update_client_profile", {"profile": profile}, ctx)
    assert outcome.content == {"saved_version": 1}
    assert ctx.down_payment_pct == Decimal("0.1")
    assert ctx.already_shown_ids == {743}
    assert profiles.profiles[0]["client_label"] == "Rav & Anna"
    assert events[0][0] == "profile" and events[0][1]["version"] == 1


async def _search_all(executor, ctx):
    return await executor.execute("search_deals", _search_input(), ctx)


@pytest.mark.asyncio
async def test_present_shortlist_rejects_unseen_duplicate_and_already_shown_ids():
    executor, profiles = _executor()
    ctx, _ = _ctx(already_shown_ids={1})
    await _search_all(executor, ctx)
    ctx.seen_ids |= {1, 6}  # pretend both twins and an already-shown deal were seen
    outcome = await executor.execute(
        "present_shortlist",
        {
            "deals": [
                {"underwriting_id": 99, "why": "x", "matched": [], "missed": []},
                {"underwriting_id": 1, "why": "x", "matched": [], "missed": []},
                {"underwriting_id": 6, "why": "x", "matched": [], "missed": []},
                {"underwriting_id": 7, "why": "x", "matched": [], "missed": []},
            ],
            "summary": "s",
        },
        ctx,
    )
    assert outcome.is_error
    reasons = " ".join(outcome.content["errors"])
    assert "99" in reasons and "already shown" in reasons and "same property" in reasons
    assert profiles.recommendations == []
    assert ctx.shortlist_presented is False


@pytest.mark.asyncio
async def test_present_shortlist_allows_fewer_than_three_only_when_searches_found_fewer():
    executor, _ = _executor()
    ctx, _ = _ctx()
    await _search_all(executor, ctx)
    one = {"deals": [{"underwriting_id": 3, "why": "x", "matched": [], "missed": []}], "summary": "s"}
    outcome = await executor.execute("present_shortlist", one, ctx)
    assert outcome.is_error
    ctx.max_candidates_seen = 1
    outcome = await executor.execute("present_shortlist", one, ctx)
    assert not outcome.is_error


@pytest.mark.asyncio
async def test_present_shortlist_writes_snapshot_and_emits_cards():
    executor, profiles = _executor()
    ctx, events = _ctx(down_payment_pct=Decimal("0.1"))
    await _search_all(executor, ctx)
    deals = [
        {"underwriting_id": i, "why": f"why {i}", "matched": ["tax"], "missed": ["pool"]}
        for i in (3, 1, 2)
    ]
    outcome = await executor.execute("present_shortlist", {"deals": deals, "summary": "Top picks"}, ctx)
    assert not outcome.is_error
    assert outcome.content == {"presented": 3}
    assert [r["rank"] for r in profiles.recommendations] == [1, 2, 3]
    first = profiles.recommendations[0]
    assert first["underwriting_id"] == 3
    assert first["snapshot"]["listing_url"] == "https://example.com/3"
    assert first["snapshot"]["total_oop"] == 390000
    assert first["match_score"] is not None
    assert ctx.shortlist_presented is True
    shortlist = [e for e in events if e[0] == "shortlist"][0][1]
    assert shortlist["summary"] == "Top picks"
    assert shortlist["cards"][0]["why"] == "why 3"


@pytest.mark.asyncio
async def test_get_deal_details_returns_text_and_marks_seen():
    executor, _ = _executor()
    ctx, _ = _ctx()
    outcome = await executor.execute("get_deal_details", {"ids": [2, 4]}, ctx)
    assert [d["id"] for d in outcome.content["deals"]] == [2, 4]
    assert outcome.content["deals"][0]["analyst_notes"] == "notes"
    assert ctx.seen_ids == {2, 4}


@pytest.mark.asyncio
async def test_find_similar_deals_ranks_by_anchor():
    executor, _ = _executor()
    ctx, _ = _ctx()
    outcome = await executor.execute(
        "find_similar_deals",
        {
            "anchor_ids": [1],
            "anchor_metrics": [],
            "anchor_states": [],
            "financing": None,
            "hard": None,
            "exclude_ids": [1],
            "limit": 3,
        },
        ctx,
    )
    assert not outcome.is_error
    assert len(outcome.content["candidates"]) == 3
    assert 1 not in _ids(outcome)


@pytest.mark.asyncio
async def test_invalid_input_returns_error_outcome():
    executor, _ = _executor()
    ctx, _ = _ctx()
    outcome = await executor.execute("search_deals", {"limit": "lots"}, ctx)
    assert outcome.is_error and "error" in outcome.content
    outcome = await executor.execute("no_such_tool", {}, ctx)
    assert outcome.is_error


def _walk(schema):
    yield schema
    for value in schema.values():
        if isinstance(value, dict):
            yield from _walk(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _walk(item)


def test_tool_schemas_are_closed_objects():
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert names == [
        "update_client_profile",
        "search_deals",
        "find_similar_deals",
        "get_deal_details",
        "present_shortlist",
    ]
    for tool in TOOL_DEFINITIONS:
        for node in _walk(tool["input_schema"]):
            assert "$ref" not in node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])


def test_union_heavy_tools_are_not_strict():
    # Strict mode limits union-typed parameters across a request; the large
    # schemas go non-strict (Pydantic still validates their input).
    strict = {t["name"]: t["strict"] for t in TOOL_DEFINITIONS}
    assert strict == {
        "update_client_profile": False,
        "search_deals": True,
        "find_similar_deals": False,
        "get_deal_details": True,
        "present_shortlist": True,
    }


def _unions(schema):
    return sum(1 for node in _walk(schema) if "anyOf" in node)


def test_strict_tools_stay_under_union_limit():
    total = sum(_unions(t["input_schema"]) for t in TOOL_DEFINITIONS if t["strict"])
    assert total <= 16
