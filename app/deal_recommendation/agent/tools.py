"""The agent's five tools: schemas the model sees, and the code that runs them.

Each tool's input is a Pydantic model; the JSON schema sent to Claude is derived
from it and made strict (every property required, nullable where optional, no
extra keys). Every number in a tool result is computed here — the model only
chooses what to look for and explains the result.
"""

import copy
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.deal_recommendation.agent.context import RunContext
from app.deal_recommendation.agent.profile import ClientProfile
from app.deal_recommendation.repositories.recommendation_repository import (
    RecommendationRepository,
)
from app.deal_recommendation.services.pool import deal_address_key, dedupe_by_address
from app.deal_recommendation.services.scoring import (
    METRICS,
    SIMILARITY_FEATURES,
    ScoredDeal,
    deal_metrics,
    score_deals,
    similar_deals,
)
from app.iron_bank.services.deal_catalog_service import CatalogDeal, DealCatalogService

LIVE_STATUSES = ["present_to_clients"]
TEXT_BOOST_WEIGHT = 2
MAX_TEXT_CHARS = 2000


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinancingInput(_Input):
    down_payment_pct: float | None = Field(
        default=None, description="0.10 for 10% down. Null uses the client profile's value."
    )
    interest_rate: float | None = Field(
        default=None, description="0.07 for 7%. Null keeps each deal's stored rate."
    )


class HardFilters(_Input):
    max_oop: float | None = Field(default=None, description="Max total out-of-pocket, USD")
    min_oop: float | None = None
    states_include: list[str] = Field(default_factory=list, description="Two-letter codes; empty = all")
    states_exclude: list[str] = Field(default_factory=list)
    min_bedrooms: int | None = None
    max_bedrooms: int | None = None
    min_purchase_price: float | None = None
    max_purchase_price: float | None = None


class Weights(_Input):
    tax_savings: int = Field(default=0, ge=0, le=5, description="Year-one tax savings, USD")
    tax_return_on_capital: int = Field(default=0, ge=0, le=5, description="Tax savings / OOP")
    m_cash_on_cash: int = Field(default=0, ge=0, le=5, description="Mid-scenario cash-on-cash")
    y1_coc_incl_tax_savings: int = Field(default=0, ge=0, le=5, description="Y1 cash-on-cash incl. tax savings")
    one_pct_ratio: int = Field(default=0, ge=0, le=5, description="Monthly mid revenue / purchase price")
    purchase_price: int = Field(default=0, ge=0, le=5, description="Higher purchase price ranks higher")
    total_oop: int = Field(default=0, ge=0, le=5, description="Lower out-of-pocket ranks higher")


class StateWeight(_Input):
    state: str
    weight: int = Field(ge=1, le=5)


class TagWeight(_Input):
    tag: str = Field(description="A boolean deal tag, e.g. turnkey, waterfront, luxury")
    weight: int = Field(ge=1, le=5)


class SearchDealsInput(_Input):
    financing: FinancingInput | None = None
    hard: HardFilters = Field(default_factory=HardFilters)
    weights: Weights = Field(default_factory=Weights)
    state_preference: list[StateWeight] = Field(default_factory=list)
    tag_preferences: list[TagWeight] = Field(default_factory=list)
    text_query: str | None = Field(
        default=None, description="Words that must appear in the deal's pitch/notes/amenity items"
    )
    text_mode: Literal["filter", "boost"] = "filter"
    exclude_ids: list[int] = Field(default_factory=list)
    limit: int = Field(default=15, ge=1, le=30)


class AnchorMetrics(_Input):
    purchase_price: float | None = None
    total_oop: float | None = None
    bedrooms: float | None = None
    tax_return_on_capital: float | None = None
    m_cash_on_cash: float | None = None
    one_pct_ratio: float | None = None


class FindSimilarInput(_Input):
    anchor_ids: list[int] = Field(default_factory=list, description="Deals the client liked")
    anchor_metrics: list[AnchorMetrics] = Field(
        default_factory=list, description="Liked deals not in the database, by their numbers"
    )
    anchor_states: list[str] = Field(default_factory=list)
    financing: FinancingInput | None = None
    hard: HardFilters | None = None
    exclude_ids: list[int] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=30)


class DealDetailsInput(_Input):
    ids: list[int] = Field(min_length=1, max_length=10)


class ShortlistItem(_Input):
    underwriting_id: int
    why: str = Field(description="2-3 sentences for the acquisition team: why this deal fits this client")
    matched: list[str] = Field(default_factory=list, description="Client preferences this deal meets")
    missed: list[str] = Field(default_factory=list, description="Client preferences this deal misses")


class PresentShortlistInput(_Input):
    deals: list[ShortlistItem] = Field(min_length=1, max_length=6)
    summary: str = Field(description="One short paragraph for the team member")


class UpdateProfileInput(_Input):
    profile: ClientProfile


_UNSUPPORTED_KEYWORDS = {
    "title",
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
}


def strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic JSON schema → strict tool schema.

    Inlines $refs, requires every property (optional ones are already nullable
    via anyOf), forbids extra keys, and drops keywords strict mode rejects.
    Pydantic re-validates the bounds when the tool runs.
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            resolved = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**resolved, **extra})
        out = {k: walk(v) for k, v in node.items() if k not in _UNSUPPORTED_KEYWORDS}
        if out.get("type") == "object" and "properties" in out:
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out

    return walk(raw)


# Strict mode caps union-typed (nullable) parameters across a request, so the
# two union-heavy schemas are sent non-strict; Pydantic validates every input.
_NON_STRICT = {"update_client_profile", "find_similar_deals"}

_TOOLS: list[tuple[str, type[BaseModel], str]] = [
    (
        "update_client_profile",
        UpdateProfileInput,
        "Record what you understood about the client from the call notes and the "
        "team member's messages. Call before the first search and whenever a "
        "preference changes. Send the full profile each time; quote the notes.",
    ),
    (
        "search_deals",
        SearchDealsInput,
        "Search the deals approved to present to clients. Hard filters remove "
        "deals; weights (0-5) rank the rest by percentile within the pool. Returns "
        "ranked candidates with a score breakdown and how many deals each filter "
        "stage removed. Numbers are recalculated at the given financing.",
    ),
    (
        "find_similar_deals",
        FindSimilarInput,
        "Find deals that look like ones the client liked: by deal id, or by the "
        "numbers of a liked deal that is not in the database.",
    ),
    (
        "get_deal_details",
        DealDetailsInput,
        "Full context for up to 10 finalists: pitch, analyst notes, amenity "
        "items, comp amenities, market, links.",
    ),
    (
        "present_shortlist",
        PresentShortlistInput,
        "Present the final 3-6 deals to the team member, best first. Only ids "
        "returned by a tool in this turn; no two deals at the same property.",
    ),
]

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": name,
        "description": description,
        "input_schema": strict_schema(model),
        "strict": name not in _NON_STRICT,
    }
    for name, model, description in _TOOLS
]
_INPUT_MODELS = {name: model for name, model, _ in _TOOLS}

TOOL_PROGRESS_LABELS: dict[str, str] = {
    "update_client_profile": "Recording the client profile",
    "search_deals": "Searching deals",
    "find_similar_deals": "Finding deals similar to ones the client liked",
    "get_deal_details": "Reading deal details",
    "present_shortlist": "Preparing the shortlist",
}


@dataclass
class ToolOutcome:
    content: dict
    is_error: bool
    summary: str


def _dec(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _money(value) -> int | None:
    return None if value is None else int(round(float(value)))


def _ratio(value) -> float | None:
    return None if value is None else round(float(value), 4)


def _clip(text: str | None) -> str | None:
    if text is None or len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:MAX_TEXT_CHARS] + "…"


class ToolExecutor:
    def __init__(self, catalog: DealCatalogService, profiles: RecommendationRepository):
        self.catalog = catalog
        self.profiles = profiles

    async def execute(self, name: str, tool_input: dict, ctx: RunContext) -> ToolOutcome:
        model = _INPUT_MODELS.get(name)
        if model is None:
            return ToolOutcome({"error": f"Unknown tool {name!r}"}, True, f"Unknown tool {name}")
        try:
            parsed = model.model_validate(tool_input)
        except ValidationError as exc:
            return ToolOutcome(
                {"error": f"Invalid input: {exc.errors(include_url=False)}"},
                True,
                "Invalid input",
            )
        handler = getattr(self, f"_{name}")
        return await handler(parsed, ctx)

    # ── pool helpers ────────────────────────────────────────────────────────

    def _financing(self, financing: FinancingInput | None, ctx: RunContext):
        down = _dec(financing.down_payment_pct) if financing else None
        rate = _dec(financing.interest_rate) if financing else None
        return (down if down is not None else ctx.down_payment_pct), (
            rate if rate is not None else ctx.interest_rate
        )

    async def _load_pool(self, ctx: RunContext, down, rate):
        override = ctx.pool_override
        result = await self.catalog.list_candidate_pool(
            statuses=override.statuses if override else LIVE_STATUSES,
            property_pending=override.property_pending if override else False,
            approved_from=override.approved_from if override else None,
            approved_to=override.approved_to if override else None,
            down_payment_pct=down,
            interest_rate=rate,
        )
        return result

    def _exclusions(self, exclude_ids: Sequence[int], ctx: RunContext) -> set[int]:
        excluded = set(exclude_ids)
        if ctx.pool_override is None:
            excluded |= ctx.already_shown_ids
        return excluded

    @staticmethod
    def _apply_hard(deals: list[CatalogDeal], hard: HardFilters | None) -> list[CatalogDeal]:
        if hard is None:
            return deals
        include = {s.upper() for s in hard.states_include}
        exclude = {s.upper() for s in hard.states_exclude}

        def within(value, low, high) -> bool:
            if low is None and high is None:
                return True
            if value is None:
                return False
            return (low is None or float(value) >= low) and (high is None or float(value) <= high)

        return [
            d
            for d in deals
            if within(d.total_oop, hard.min_oop, hard.max_oop)
            and within(d.purchase_price, hard.min_purchase_price, hard.max_purchase_price)
            and within(d.bedrooms, hard.min_bedrooms, hard.max_bedrooms)
            and (not include or (d.state or "").upper() in include)
            and (d.state or "").upper() not in exclude
        ]

    def _candidate(self, scored: ScoredDeal, rate_is_stored: bool) -> dict:
        deal, m = scored.deal, scored.metrics
        return {
            "id": deal.id,
            "address": deal.property_address or deal.street,
            "city": deal.city,
            "state": deal.state,
            "bedrooms": deal.bedrooms,
            "purchase_price": _money(deal.purchase_price),
            "total_oop": _money(deal.total_oop),
            "tax_savings": _money(deal.tax_savings),
            "tax_return_on_capital": _ratio(m["tax_return_on_capital"]),
            "m_cash_on_cash": _ratio(m["m_cash_on_cash"]),
            "y1_coc_incl_tax_savings": _ratio(m["y1_coc_incl_tax_savings"]),
            "one_pct_ratio": _ratio(m["one_pct_ratio"]),
            "down_payment_pct": _ratio(deal.down_payment_pct),
            "interest_rate": _ratio(deal.interest_rate),
            "interest_rate_is_stored": rate_is_stored,
            "score": scored.score,
            "breakdown": scored.breakdown,
            "missing": scored.missing,
            "turnkey": deal.boolean_tags.get("turnkey", False),
            "category_tags": {k: v for k, v in deal.category_tags.items() if v},
        }

    def _remember(self, ctx: RunContext, ranked: list[ScoredDeal]) -> None:
        for scored in ranked:
            ctx.seen_ids.add(scored.deal.id)
            ctx.last_scores[scored.deal.id] = scored.score
        ctx.max_candidates_seen = max(ctx.max_candidates_seen, len(ranked))

    # ── tools ───────────────────────────────────────────────────────────────

    async def _update_client_profile(self, parsed: UpdateProfileInput, ctx: RunContext):
        profile = parsed.profile
        version = await self.profiles.add_profile(
            conversation_id=ctx.conversation_id,
            run_id=ctx.run_id,
            profile=profile.model_dump(mode="json"),
        )
        ctx.down_payment_pct = _dec(profile.financing.down_payment_pct)
        ctx.interest_rate = _dec(profile.financing.interest_rate)
        ctx.already_shown_ids = set(profile.already_shown_ids)
        await ctx.emit("profile", {"profile": profile.model_dump(mode="json"), "version": version})
        return ToolOutcome({"saved_version": version}, False, f"Saved client profile v{version}")

    async def _search_deals(self, parsed: SearchDealsInput, ctx: RunContext):
        down, rate = self._financing(parsed.financing, ctx)
        pool = await self._load_pool(ctx, down, rate)
        deals = dedupe_by_address(pool.deals)
        counts = {
            "pool": len(pool.deals),
            "dropped_unrecalculable": pool.dropped_unrecalculable,
            "after_dedupe": len(deals),
        }
        deals = self._apply_hard(deals, parsed.hard)
        counts["after_hard_filters"] = len(deals)

        boost_ids: set[int] = set()
        if parsed.text_query and deals:
            hits = await self.catalog.text_search([d.id for d in deals], parsed.text_query)
            if parsed.text_mode == "filter":
                deals = [d for d in deals if d.id in hits]
            else:
                boost_ids = hits
        counts["after_text_filter"] = len(deals)

        excluded = self._exclusions(parsed.exclude_ids, ctx)
        deals = [d for d in deals if d.id not in excluded]
        counts["after_exclusions"] = len(deals)

        ranked = score_deals(
            deals,
            weights=parsed.weights.model_dump(),
            state_preference={s.state: s.weight for s in parsed.state_preference},
            tag_preferences={t.tag: t.weight for t in parsed.tag_preferences},
            text_boost_ids=boost_ids,
            text_boost_weight=TEXT_BOOST_WEIGHT if boost_ids else 0,
        )[: parsed.limit]
        self._remember(ctx, ranked)
        rate_is_stored = rate is None
        down_label = f" at {float(down):.0%} down" if down is not None else ""
        return ToolOutcome(
            {
                "stage_counts": counts,
                "candidates": [self._candidate(s, rate_is_stored) for s in ranked],
            },
            False,
            f"{len(ranked)} candidates{down_label} "
            f"({counts['after_dedupe']} in pool → {counts['after_exclusions']} after filters)",
        )

    async def _find_similar_deals(self, parsed: FindSimilarInput, ctx: RunContext):
        down, rate = self._financing(parsed.financing, ctx)
        pool = await self._load_pool(ctx, down, rate)
        all_deals = dedupe_by_address(pool.deals)
        by_id = {d.id: d for d in pool.deals}
        anchors = [deal_metrics(by_id[i]) for i in parsed.anchor_ids if i in by_id]
        anchors += [a.model_dump() for a in parsed.anchor_metrics]
        if not anchors:
            return ToolOutcome(
                {"error": "No usable anchors: anchor_ids not in the pool and no anchor_metrics."},
                True,
                "No usable anchors",
            )
        anchor_states = {s.upper() for s in parsed.anchor_states}
        anchor_states |= {(by_id[i].state or "").upper() for i in parsed.anchor_ids if i in by_id}
        excluded = self._exclusions(parsed.exclude_ids, ctx)
        deals = [d for d in self._apply_hard(all_deals, parsed.hard) if d.id not in excluded]
        ranked = similar_deals(
            deals,
            anchors=[{k: v for k, v in a.items() if k in SIMILARITY_FEATURES} for a in anchors],
            anchor_states=anchor_states,
        )[: parsed.limit]
        self._remember(ctx, ranked)
        return ToolOutcome(
            {"candidates": [self._candidate(s, rate is None) for s in ranked]},
            False,
            f"{len(ranked)} similar deals",
        )

    async def _get_deal_details(self, parsed: DealDetailsInput, ctx: RunContext):
        down, rate = ctx.down_payment_pct, ctx.interest_rate
        details = await self.catalog.get_details(
            parsed.ids, down_payment_pct=down, interest_rate=rate
        )
        out = []
        for d in details:
            scored = ScoredDeal(
                deal=d.deal,
                metrics=deal_metrics(d.deal),
                score=ctx.last_scores.get(d.deal.id, 0.0),
            )
            ctx.seen_ids.add(d.deal.id)
            out.append(
                {
                    **self._candidate(scored, rate is None),
                    "deal_pitch": _clip(d.deal_pitch),
                    "note": _clip(d.note),
                    "analyst_notes": _clip(d.analyst_notes),
                    "construction_and_design_notes": _clip(d.construction_and_design_notes),
                    "optimization_items": [
                        {**item, "total_price": _money(item.get("total_price"))}
                        for item in d.optimization_items
                    ],
                    "comp_amenity_counts": d.comp_amenity_counts,
                    "market_name": d.market_name,
                    "listing_url": d.listing_url,
                    "video_walkthrough": d.video_walkthrough,
                    "loom_vid": d.loom_vid,
                }
            )
        return ToolOutcome({"deals": out}, False, f"Read details for {len(out)} deals")

    async def _present_shortlist(self, parsed: PresentShortlistInput, ctx: RunContext):
        down, rate = ctx.down_payment_pct, ctx.interest_rate
        pool = await self._load_pool(ctx, down, rate)
        by_id = {d.id: d for d in pool.deals}
        ids = [item.underwriting_id for item in parsed.deals]

        errors = []
        for i in ids:
            if i not in ctx.seen_ids:
                errors.append(f"Deal {i} was not returned by any tool in this turn.")
            elif i not in by_id:
                errors.append(f"Deal {i} is no longer in the candidate pool.")
            if ctx.pool_override is None and i in ctx.already_shown_ids:
                errors.append(f"Deal {i} was already shown to the client.")
        keys: dict[str, int] = {}
        for i in ids:
            if i in by_id:
                key = deal_address_key(by_id[i])
                if key in keys:
                    errors.append(f"Deals {keys[key]} and {i} are the same property.")
                keys.setdefault(key, i)
        if len(set(ids)) != len(ids):
            errors.append("A deal is listed twice.")
        minimum = 3 if ctx.max_candidates_seen >= 3 else 1
        if len(ids) < minimum:
            errors.append(f"Present at least {minimum} deals (searches found enough candidates).")
        if errors:
            return ToolOutcome({"errors": errors}, True, "Shortlist rejected")

        details = {
            d.deal.id: d
            for d in await self.catalog.get_details(ids, down_payment_pct=down, interest_rate=rate)
        }
        items, cards = [], []
        for rank, item in enumerate(parsed.deals, start=1):
            deal = by_id[item.underwriting_id]
            detail = details.get(deal.id)
            scored = ScoredDeal(deal=deal, metrics=deal_metrics(deal), score=0.0)
            snapshot = {
                k: v
                for k, v in self._candidate(scored, rate is None).items()
                if k not in ("score", "breakdown", "missing")
            }
            snapshot.update(
                listing_url=detail.listing_url if detail else None,
                video_walkthrough=detail.video_walkthrough if detail else None,
                loom_vid=detail.loom_vid if detail else None,
                market_name=detail.market_name if detail else None,
            )
            match_score = ctx.last_scores.get(deal.id)
            items.append(
                {
                    "rank": rank,
                    "underwriting_id": deal.id,
                    "match_score": match_score,
                    "why": item.why,
                    "matched": item.matched,
                    "missed": item.missed,
                    "snapshot": json.loads(json.dumps(snapshot, default=str)),
                }
            )
            cards.append({**items[-1]})
        await self.profiles.add_recommendations(
            run_id=ctx.run_id, conversation_id=ctx.conversation_id, items=items
        )
        ctx.shortlist_presented = True
        await ctx.emit("shortlist", {"cards": cards, "summary": parsed.summary})
        return ToolOutcome({"presented": len(items)}, False, f"Presented {len(items)} deals")


__all__ = [
    "METRICS",
    "TOOL_DEFINITIONS",
    "TOOL_PROGRESS_LABELS",
    "ToolExecutor",
    "ToolOutcome",
    "strict_schema",
]
