# Deal Recommendation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A chat tool where an acquisition team member pastes a Fathom call summary and a Claude agent returns 4–5 `present_to_clients` deals with reasons, refinable by chat.

**Architecture:** A new `app/deal_recommendation/` domain in adus-be runs a Claude agent using the Anthropic SDK's Tool Runner (which does the call-tools-and-repeat looping), streaming, over five tools. The tools read deals through one read-only iron_bank facade, `DealCatalogService`, and score them deterministically in Python. Every message, run, tool call, profile and recommendation is persisted in a new `deal_recommendation` schema, and results stream to the browser over SSE. A new Next.js app (`../deal-recommendation-fe`) proxies to adus-be with a server-side API key and renders a chat thread with deal cards.

**Tech Stack:** FastAPI, async SQLAlchemy 2, Alembic, asyncpg, pytest + pytest-asyncio, `anthropic` Python SDK (`AsyncAnthropic`), Next.js (App Router, TypeScript), Tailwind, vitest.

**Spec:** `docs/superpowers/specs/2026-10-17-deal-recommendation-v1-design.md`. Read it before any task. Eval data: `docs/superpowers/plans/2026-10-17-deal-recommendation-v1-eval-cases.json`.

**Nudge storage (changed in final review):** the nudge is stored as a `user` text-block message, not a mid-conversation `system` message — the API only accepts a system message right after a user turn, and the nudge follows an assistant turn. `messages.role` stays `('user','assistant')` as in the spec.

## Global Constraints

- Work on branch `feat/deal-recommendation-v1` off `develop` in adus-be. The frontend is a new git repo at `/Users/tarifulislam/Documents/str-projects/adus-project/deal-recommendation-fe`.
- Domain rule: `app/deal_recommendation/**` may import from `app/core/**` and from **exactly one** iron_bank module, `app/iron_bank/services/deal_catalog_service.py`. No other cross-domain import.
- `DealCatalogService` never writes, and returns dataclasses, never ORM objects.
- DB schema `deal_recommendation`, Alembic branch label `deal_recommendation`, version table stays in `markets`.
- Agent loop: the SDK Tool Runner (`client.beta.messages.tool_runner(..., stream=True)`), not a hand-written loop.
- Model `claude-sonnet-5-5`; `thinking={"type": "adaptive"}`; `output_config={"effort": settings.DEAL_REC_EFFORT}` (default `"high"`); `max_tokens=64000`; streaming; top-level `cache_control={"type": "ephemeral"}`; `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`. If the installed SDK rejects `fallbacks` as a kwarg, pass it via `extra_body={"fallbacks": "default"}`.
- Never send forced `tool_choice` (it's a 400 on this model). Tools are `strict: true` with `additionalProperties: false`.
- `messages.content` is stored exactly as sent to or received from Claude (`block.to_dict()` for response blocks) and never rewritten. History = rows in `seq` order.
- An assistant message containing `tool_use` blocks and the user message carrying its `tool_result` blocks are written in **one transaction**, so stored history never has an unanswered `tool_use`.
- Candidate pool (live): `deal_status = 'present_to_clients'`, `property_pending = false`, recalculable (has `purchase_details` and `forecasted_revenue`), deduped by normalized address.
- Pool (eval override): statuses `present_to_clients` + `client_under_contract`, `deal_approved` within the case window, no `property_pending` filter, recalculable, deduped.
- All numbers on cards and in tool outputs are computed by our code at the run's financing. The LLM never computes numbers.
- Cost constants for `claude-sonnet-5-5` (USD per 1M tokens): input 2.00, output 10.00, cache read 0.20, cache write 2.50.
- Tool-call cap per run: `DEAL_REC_MAX_TOOL_CALLS` (default 12).
- API prefix `/deal-recommendation`. The global auth guard is unchanged, and these routes are not added to `PUBLIC_PATHS`.
- `ANTHROPIC_API_KEY` is read from adus-be `.env`. The user provides the key, so ask for it at Task 6. Never commit it.

## Review Focus

1. **Unusable paste** (a meeting summary with no investment criteria, or random text). Expect the agent to ask one clarifying question. The run finishes `succeeded` with no shortlist, and the nudge does not fire, because the reply ends with a question. Test in Task 6.
2. **A search that filters everything out** (budget below every deal). Expect `search_deals` to return `candidates: []` with stage counts showing where they went. `present_shortlist` accepts fewer than 3 deals only when no search in the run returned 3 or more candidates. Tests in Tasks 5 and 3.
3. **A second message while a run is going.** Expect HTTP 409, and the first run unaffected. A run stuck in `running` for more than 15 minutes (server restarted) does not block new runs. Test in Task 7.
4. **The browser disconnects mid-stream.** Expect the run to keep going and to persist messages, recommendations and its finished status. Test in Task 7.
5. **The Claude API errors mid-run** (5xx after retries, or `stop_reason: "refusal"`). Expect the run marked `failed` with the error, an `error` SSE event, and stored history that is still valid for the next turn (no dangling `tool_use`). Test in Task 6.

---

### Task 1: iron_bank read facade `DealCatalogService`

**Files:**
- Create: `app/iron_bank/services/deal_catalog_service.py`
- Modify: `app/iron_bank/repositories/underwriting_repository.py` (add two read methods)
- Modify: `app/iron_bank/services/simulate_underwritings_service.py` (rename `_simulate_row` → `simulate_row`, update its one caller in `get_all_simulated`)
- Test: `tests/iron_bank/test_deal_catalog_service.py`

**Interfaces:**
- Consumes: `UnderwritingRepository`, `SimulateUnderwritingsService(repository, calculator=...)`, `UnderwritingCalculator`.
- Produces (all in `deal_catalog_service.py`):
  ```python
  @dataclass(frozen=True)
  class CatalogDeal:
      id: int
      property_address: str | None
      street: str | None
      city: str | None
      state: str | None
      bedrooms: int | None
      bathrooms: Decimal | None
      market_id: int | None
      deal_status: str
      deal_approved: datetime | None
      purchase_price: Decimal | None
      total_oop: Decimal
      l_cash_on_cash: Decimal | None
      m_cash_on_cash: Decimal | None
      h_cash_on_cash: Decimal | None
      y1_coc_incl_tax_savings_mid: Decimal | None   # simulated y1_coc_incl_tax_savings["mid_pct"]
      tax_savings: Decimal | None
      mid_gross_revenue: Decimal | None
      down_payment_pct: Decimal | None              # effective, from simulated purchase_details
      interest_rate: Decimal | None                 # effective, from simulated purchase_details
      boolean_tags: dict[str, bool]                 # the BOOLEAN_TAG_FIELDS columns
      category_tags: dict[str, str | list[str] | None]  # REFERENCE_TAG_FIELDS columns

  @dataclass(frozen=True)
  class PoolResult:
      deals: list[CatalogDeal]
      dropped_unrecalculable: int

  @dataclass(frozen=True)
  class CatalogDealDetails:
      deal: CatalogDeal
      deal_pitch: str | None
      note: str | None
      analyst_notes: str | None
      construction_and_design_notes: str | None
      optimization_items: list[dict[str, Any]]      # keys: category, spec, tier, notes, total_price
      comp_amenity_counts: dict[str, int]           # e.g. {"has_pool": 3, "has_pickleball": 0, ...}, true-counts over the comp set
      listing_url: str | None
      video_walkthrough: str | None
      loom_vid: str | None
      market_name: str | None

  class DealCatalogService:
      def __init__(self, repository: UnderwritingRepository, calculator: UnderwritingCalculator | None = None): ...
      async def list_candidate_pool(
          self, *, statuses: Sequence[str], property_pending: bool | None = False,
          approved_from: date | None = None, approved_to: date | None = None,
          down_payment_pct: Decimal | None = None, interest_rate: Decimal | None = None,
      ) -> PoolResult: ...
      async def text_search(self, ids: Sequence[int], query: str) -> set[int]: ...
      async def get_details(
          self, ids: Sequence[int], *, down_payment_pct: Decimal | None = None,
          interest_rate: Decimal | None = None,
      ) -> list[CatalogDealDetails]: ...
  ```
- Repository additions:
  - `UnderwritingRepository.get_recommendation_pool_rows(*, statuses, property_pending, min_deal_approved, max_deal_approved) -> list[Row]`. It selects every column `get_simulation_inputs` selects, plus `property_address, street, city, state, bedrooms, bathrooms, market_id, deal_status, mid_gross_revenue` and all boolean and category tag columns. It has no pagination and no status exclusion list beyond `statuses`.
  - `UnderwritingRepository.search_text(ids, terms: list[str]) -> set[int]`. It returns the ids where **every** term ILIKE-matches at least one of: `underwritings.deal_pitch`, `underwritings.note`, `uw_details.analyst_notes`, `uw_details.construction_and_design_notes`, `uw_optimization_items.category/spec/notes`. Optimization items are matched through `EXISTS`, not a join, so rows don't multiply.

- [ ] **Step 0: Create the branch**

Run: `git checkout develop && git pull && git checkout -b feat/deal-recommendation-v1`

- [ ] **Step 1: Write failing tests** in `tests/iron_bank/test_deal_catalog_service.py`, using a `FakeRepository` that returns `SimpleNamespace` rows (pattern: `tests/iron_bank/test_get_underwriting_service.py`):
  - `test_pool_drops_rows_without_purchase_details_or_forecast`: 3 rows, one with `purchase_details=None` and one with `forecasted_revenue=None` → `len(result.deals) == 1`, `result.dropped_unrecalculable == 2`.
  - `test_pool_recalculates_at_requested_down_payment`: one row stored at `down_payment_pct=0.2` → with `down_payment_pct=Decimal("0.1")` the deal's `down_payment_pct == Decimal("0.1")`, and `total_oop` is lower than the stored value.
  - `test_pool_passes_filters_to_repository`: assert the fake received `statuses=["present_to_clients","client_under_contract"]`, `property_pending=None`, `min_deal_approved=date(2026,2,15)`, `max_deal_approved=date(2026,5,20)`.
  - `test_text_search_splits_terms_and_lowercases`: `text_search([1,2], "Pickleball  Lake")` calls `search_text([1,2], ["pickleball","lake"])`. An empty or whitespace query returns `set(ids)` without calling the repo.
  - `test_get_details_counts_comp_amenities`: two comps, `has_pool` True/True, `has_pickleball` True/None → `{"has_pool": 2, "has_pickleball": 1, ...}`.

  Build row fixtures with real-shaped `purchase_details` and `forecasted_revenue` dicts copied from an existing simulation test (`grep -rn "forecasted_revenue" tests/iron_bank`) so the calculator runs.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/iron_bank/test_deal_catalog_service.py -v`
Expected: FAIL (`ModuleNotFoundError: app.iron_bank.services.deal_catalog_service`).

- [ ] **Step 3: Implement** the repository methods, the `simulate_row` rename, and `DealCatalogService`. Use `SimulateUnderwritingsService(repository, calculator=calculator).simulate_row(row, interest_rate, down_payment_pct)` and drop rows where `simulated is False`, counting them in `dropped_unrecalculable`. Build `CatalogDeal` from the simulated row (`total_oop`, CoC, `purchase_details`, `y1_coc_incl_tax_savings`) plus the pass-through display columns. `get_details` reuses `list_candidate_pool`-style simulation for the ids, and uses `repository.get_by_ids(ids)` for children (check it loads `detail`, `optimization_items` and `comp_set`; add `selectinload`s there if not). `market_name` comes from a single `select(MarketKeysMaster.id, MarketKeysMaster.market_name)` over the market ids. iron_bank already depends on markets, so this adds no new domain edge.

- [ ] **Step 4: Run tests and confirm they pass, including existing simulation tests**

Run: `uv run pytest tests/iron_bank -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/iron_bank tests/iron_bank/test_deal_catalog_service.py
git commit -m "feat(iron_bank): add read-only DealCatalogService facade for deal recommendation"
```

---

### Task 2: Pool dedupe and address normalization

**Files:**
- Create: `app/deal_recommendation/__init__.py`, `app/deal_recommendation/services/__init__.py`, `app/deal_recommendation/services/pool.py`
- Test: `tests/deal_recommendation/__init__.py`, `tests/deal_recommendation/test_pool.py`

**Interfaces:**
- Consumes: `CatalogDeal` (Task 1).
- Produces:
  - `normalize_address(property_address: str | None, street: str | None, city: str | None, state: str | None) -> str`
  - `dedupe_by_address(deals: Sequence[CatalogDeal]) -> list[CatalogDeal]`: keeps one deal per normalized address, preferring the latest `deal_approved` (None counts as oldest), then the highest `id`. Output keeps input order of the kept deals.

- [ ] **Step 1: Write failing tests** (`test_pool.py`), parametrized with real strings from the dev DB:
  - `"12664 115th St, Largo, FL 33778 | MLS #TB8509860 | Zillow"` and `"12664 115th St, Largo, FL 33778"` → equal.
  - `"(4BD) 6431 S Lagoon Dr, Panama City Beach, FL 32408"` and `"(5BD) 6431 S Lagoon Dr, Panama City Beach, FL 32408"` → equal.
  - `"1004 SW 19 Street, Fort Lauderdale, FL 33315"` and `"1004 sw 19 st, fort lauderdale, fl 33315"` → equal (suffix map: street→st, road→rd, drive→dr, lane→ln, avenue→ave, court→ct, terrace→ter, trail→trl, turnpike→tpke).
  - `"1 Vista Ridge Dr, Galena, IL 61036"` vs `"Vista Ridge Dr, East Jewett, NY"` → **not** equal.
  - `"Off Market 5 bed: Broken Bow"` twice → equal; `None` address falls back to `street + city + state`.
  - `test_dedupe_keeps_latest_approved`: ids 818 (approved 2026-03-11) and 1060 (2026-04-22), same address → keeps 1060.
  - `test_dedupe_tie_breaks_on_highest_id`: both `deal_approved=None` → keeps the higher id.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/deal_recommendation/test_pool.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** `pool.py`. Normalization in order:
  1. Prefer `property_address`, else join `street, city, state`.
  2. Lowercase.
  3. Drop everything from the first `|`.
  4. Drop a leading parenthesized group.
  5. Drop the ZIP (`\b\d{5}(-\d{4})?\b`).
  6. Replace punctuation with spaces.
  7. Apply the suffix map per token.
  8. Collapse whitespace.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `uv run pytest tests/deal_recommendation/test_pool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/deal_recommendation tests/deal_recommendation
git commit -m "feat(deal_recommendation): address normalization and pool dedupe"
```

---

### Task 3: Deterministic scoring and similarity

**Files:**
- Create: `app/deal_recommendation/services/scoring.py`
- Test: `tests/deal_recommendation/test_scoring.py`

**Interfaces:**
- Consumes: `CatalogDeal`.
- Produces:
  ```python
  METRICS: tuple[str, ...] = ("tax_savings", "tax_return_on_capital", "m_cash_on_cash",
                              "y1_coc_incl_tax_savings", "one_pct_ratio", "purchase_price", "total_oop")
  LOWER_IS_BETTER: frozenset[str] = frozenset({"total_oop"})
  MISSING_PERCENTILE = 0.25
  SIMILARITY_FEATURES = ("purchase_price", "total_oop", "bedrooms", "tax_return_on_capital",
                         "m_cash_on_cash", "one_pct_ratio")

  def deal_metrics(deal: CatalogDeal) -> dict[str, float | None]
      # tax_return_on_capital = tax_savings / total_oop; one_pct_ratio = (mid_gross_revenue / 12) / purchase_price;
      # y1_coc_incl_tax_savings = deal.y1_coc_incl_tax_savings_mid; bedrooms included for similarity

  @dataclass
  class ScoredDeal:
      deal: CatalogDeal
      metrics: dict[str, float | None]
      score: float                     # 0..100, rounded to 1 dp
      breakdown: dict[str, float]      # component -> points contributed (0..100 scale)
      missing: list[str]               # weighted metrics that were None

  def score_deals(deals: Sequence[CatalogDeal], *, weights: Mapping[str, int],
                  state_preference: Mapping[str, int] | None = None,
                  tag_preferences: Mapping[str, int] | None = None,
                  text_boost_ids: set[int] | None = None, text_boost_weight: int = 0) -> list[ScoredDeal]

  def similar_deals(deals: Sequence[CatalogDeal], *, anchors: Sequence[Mapping[str, float]],
                    anchor_states: set[str]) -> list[ScoredDeal]
  ```

Scoring rules (not determined by the signatures):
- **Percentile** of a value within the pool's non-null values for that metric: `count(v < x) / (n - 1)` for `n > 1`, and `0.5` for `n == 1`. For `LOWER_IS_BETTER` use `1 - p`. A None value gets `MISSING_PERCENTILE`.
- **Raw score** = Σ `weight × percentile` over weighted metrics. Add the state preference weight if the deal's state (uppercased) is in `state_preference`. Add the tag preference weight if `deal.boolean_tags[tag]` is True. Add `text_boost_weight` if the id is in `text_boost_ids`.
- **Max** = Σ metric weights + max(state weights, default 0) + Σ tag weights + `text_boost_weight`. `score = 100 × raw / max`, or 0 if max is 0. Breakdown values use the same `100 / max` scale.
- **Sort** by score desc, then id asc.
- **Similarity:** percentile-normalize each feature within the pool. An anchor's value maps to its percentile against the pool's values, by the same rule. Distance = mean abs diff over the features both have. With several anchors, take the minimum distance. `similarity = 1 - distance`, +0.1 if the deal's state is in `anchor_states`. `score = 100 × similarity / 1.1`. Breakdown keys: `"distance"`, `"state_match"`.

- [ ] **Step 1: Write failing tests:**
  - `test_metrics_computes_ratios`: tax 155000, oop 212000 → `tax_return_on_capital ≈ 0.7311`; mid_gross 120000, pp 1000000 → `one_pct_ratio == 0.01`.
  - `test_higher_weighted_metric_ranks_first`: two deals, A higher tax, B higher CoC; `weights={"tax_savings":5,"m_cash_on_cash":1}` → A first; flip the weights → B first.
  - `test_missing_metric_scores_25th_percentile_and_is_listed`: three deals, one with `tax_savings=None` → its `missing == ["tax_savings"]` (only when weighted) and its tax component equals `100*5*0.25/5`.
  - `test_total_oop_lower_is_better`.
  - `test_state_preference_adds_bonus`: `state_preference={"FL": 2}` lifts the FL deal above an otherwise-equal GA deal.
  - `test_scores_are_bounded_0_100` and `test_no_weights_gives_zero_scores`.
  - `test_similar_deals_prefers_closest_anchor_and_same_state`: an anchor `{"total_oop":212000,"tax_return_on_capital":0.73}`, state `{"GA"}` → the GA deal with oop 210k and ratio 0.7 ranks first.
  - `test_empty_pool_returns_empty_list` for both functions.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/deal_recommendation/test_scoring.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** `scoring.py` per the rules above.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `uv run pytest tests/deal_recommendation/test_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/deal_recommendation/services/scoring.py tests/deal_recommendation/test_scoring.py
git commit -m "feat(deal_recommendation): percentile scoring and similarity"
```

---

### Task 4: Schema, models, migrations, repositories, docs

**Files:**
- Create: `app/deal_recommendation/models/__init__.py`, `models/conversation.py` (Conversation, Message), `models/run.py` (AgentRun, ToolCall), `models/recommendation.py` (ClientProfileVersion, Recommendation)
- Create: `migrations/versions/<rev>_init_deal_recommendation.py` (empty schema, `branch_labels=("deal_recommendation",)`, `down_revision=None`, same shape as `356bce2d2f9d_init_discussions.py`)
- Create: `migrations/versions/<rev>_create_deal_recommendation_tables.py` (autogenerate, then review)
- Modify: `migrations/env.py` (import `app.deal_recommendation.models`; add `"deal_recommendation"` to `TARGET_SCHEMAS`)
- Create: `app/deal_recommendation/repositories/__init__.py`, `conversation_repository.py`, `run_repository.py`, `recommendation_repository.py`
- Modify: `CLAUDE.md`: add the domain row (`app/deal_recommendation/` → `deal_recommendation`), add `deal_recommendation` to the managed schemas and Alembic branch lists (six branches), and add under Model Conventions: "Exception: `app/deal_recommendation` may import `app/iron_bank/services/deal_catalog_service.py` (read-only facade) and nothing else from another domain."
- Test: `tests/deal_recommendation/test_models.py`

**Interfaces:**
- Tables: exactly spec §7, with these specifics:
  - `messages.role` CHECK in (`'user'`, `'assistant'`, `'system'`).
  - `agent_runs.status` CHECK in (`'running'`, `'succeeded'`, `'failed'`, `'capped'`).
  - `conversations.status` CHECK in (`'active'`, `'archived'`), default `'active'`.
  - Index `(conversation_id, seq)` unique on `messages`; index on `tool_calls.run_id`, `recommendations.run_id`, `client_profiles.conversation_id`.
  - `created_by_user_id` FK `users.users.id ON DELETE SET NULL`. This FK into another *schema* is allowed; `iron_bank.underwritings` gets **no** FK.
- Repositories (each takes `AsyncSession`; callers own commit):
  ```python
  class ConversationRepository:
      async def create(self, *, title: str | None, created_by_user_id: int | None, model: str) -> Conversation
      async def get(self, conversation_id: UUID) -> Conversation | None
      async def list_recent(self, limit: int = 50) -> list[Conversation]
      async def append_messages(self, conversation_id: UUID, items: Sequence[tuple[str, list[dict] | str]]) -> list[Message]
          # assigns seq = max(seq)+1.. in order, touches conversations.updated_at
      async def load_history(self, conversation_id: UUID) -> list[dict]   # [{"role":..., "content":...}] in seq order
      async def list_messages(self, conversation_id: UUID) -> list[Message]

  class RunRepository:
      async def create_run(self, *, conversation_id: UUID, user_message_id: int, model: str, effort: str) -> AgentRun
      async def finish_run(self, run_id: UUID, *, status: str, stop_reason: str | None, iterations: int,
                           usage: RunUsage, error: str | None) -> None
      async def add_tool_call(self, *, run_id: UUID, seq: int, tool_use_id: str, tool_name: str,
                              input: dict, output: dict, is_error: bool, duration_ms: int) -> None
      async def has_active_run(self, conversation_id: UUID, *, stale_after: timedelta = timedelta(minutes=15)) -> bool
      async def get_trace(self, run_id: UUID) -> tuple[AgentRun, list[ToolCall]] | None
      async def list_runs(self, conversation_id: UUID) -> list[AgentRun]

  @dataclass
  class RunUsage:   # in run_repository.py
      input_tokens: int = 0; output_tokens: int = 0; cache_read_tokens: int = 0; cache_write_tokens: int = 0
      def cost_usd(self) -> Decimal   # Global Constraints rates, quantized to 0.0001

  class RecommendationRepository:
      async def add_profile(self, *, conversation_id: UUID, run_id: UUID, profile: dict) -> int   # returns version (1-based)
      async def latest_profile(self, conversation_id: UUID) -> dict | None
      async def list_profiles(self, conversation_id: UUID) -> list[ClientProfileVersion]
      async def add_recommendations(self, *, run_id: UUID, conversation_id: UUID, items: Sequence[dict]) -> None
          # each item: rank, underwriting_id, match_score, why, matched, missed, snapshot
      async def list_for_conversation(self, conversation_id: UUID) -> list[Recommendation]
  ```

- [ ] **Step 1: Write failing tests** (`test_models.py`) using SQLAlchemy metadata only, with no DB:
  - `test_tables_live_in_deal_recommendation_schema`: all six tables in `Base.metadata` have `schema == "deal_recommendation"`.
  - `test_message_role_check_allows_system`: compile the CHECK constraint text and assert `'system'` is in it.
  - `test_recommendations_has_no_fk_to_iron_bank`.
  - `test_run_usage_cost`: `RunUsage(1_000_000, 100_000, 2_000_000, 0).cost_usd() == Decimal("3.4000")` (2.00 + 1.00 + 0.40).

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/deal_recommendation/test_models.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** the models, repositories and `env.py` change. Then generate the migration: `uv run alembic revision -m "init_deal_recommendation" --head base --branch-label deal_recommendation` (edit to `CREATE SCHEMA IF NOT EXISTS deal_recommendation`), then `uv run alembic revision --autogenerate -m "create_deal_recommendation_tables" --head deal_recommendation@head`. Review the autogenerated file: it must touch only `deal_recommendation` tables.

- [ ] **Step 4: Run tests, apply the migration to the dev DB, and check heads**

Run: `uv run pytest tests/deal_recommendation -v && uv run alembic upgrade deal_recommendation@head && uv run alembic heads`
Expected: tests PASS. Upgrade succeeds. `heads` lists six heads, including `(deal_recommendation)`. **Ask the user before running the upgrade against any non-dev database.**

- [ ] **Step 5: Commit**

```bash
git add app/deal_recommendation migrations CLAUDE.md tests/deal_recommendation/test_models.py
git commit -m "feat(deal_recommendation): schema, models, migrations, repositories"
```

---

### Task 5: Client profile, tool definitions, tool executor

**Files:**
- Create: `app/deal_recommendation/agent/__init__.py`, `agent/profile.py`, `agent/context.py`, `agent/tools.py`
- Test: `tests/deal_recommendation/test_tools.py`

**Interfaces:**
- Consumes: `DealCatalogService` (Task 1), `dedupe_by_address` (Task 2), `score_deals`, `similar_deals`, `deal_metrics` (Task 3), `RecommendationRepository`, `RunRepository` (Task 4).
- Produces:
  ```python
  # profile.py — Pydantic v2 models mirroring spec §5.4 exactly, plus:
  class ClientProfile(BaseModel):  # fields per spec §5.4, all optional except client_label
      already_shown_ids: list[int] = []
  # Every quote-carrying sub-model has `quote: str | None`.

  # context.py
  @dataclass
  class PoolOverride:
      statuses: list[str]; approved_from: date; approved_to: date; property_pending: bool | None = None
  @dataclass
  class RunContext:
      conversation_id: UUID
      run_id: UUID
      down_payment_pct: Decimal | None        # from latest profile; updated by update_client_profile
      interest_rate: Decimal | None
      already_shown_ids: set[int]
      seen_ids: set[int] = field(default_factory=set)     # ids returned by any tool this run
      max_candidates_seen: int = 0                         # largest candidate list any search returned this run
      shortlist_presented: bool = False
      pool_override: PoolOverride | None = None           # eval only; never exposed to the model
      emit: Callable[[str, dict], Awaitable[None]] = _noop

  # tools.py
  TOOL_DEFINITIONS: list[dict]   # five tools, strict, additionalProperties false; names below
  TOOL_PROGRESS_LABELS: dict[str, str]
  @dataclass
  class ToolOutcome:
      content: dict; is_error: bool
      summary: str   # one line for the live UI, e.g. "42 candidates (707 in pool → 120 after filters)", "Saved profile v2", "Details for 6 deals", "Presented 5 deals"
      
  class ToolExecutor:
      def __init__(self, catalog: DealCatalogService, profiles: RecommendationRepository, session: AsyncSession): ...
      async def execute(self, name: str, tool_input: dict, ctx: RunContext) -> ToolOutcome
  ```
- Tool names and input shapes (spec §5.3):
  - `update_client_profile`: `{profile: ClientProfile JSON schema}` → saves a version, sets `ctx.down_payment_pct`, `ctx.interest_rate` and `ctx.already_shown_ids`, emits `("profile", {"profile":..., "version": n})`, returns `{"saved_version": n}`.
  - `search_deals`: `{financing:{down_payment_pct, interest_rate|null}, hard:{max_oop, min_oop|null, states_include[], states_exclude[], min_bedrooms|null, max_bedrooms|null, min_purchase_price|null, max_purchase_price|null}, weights:{<METRICS name>: 0..5}, state_preference:[{state, weight}], tag_preferences:[{tag, weight}], text_query|null, text_mode:"filter"|"boost", exclude_ids[], limit}` (limit default 15, max 30).
  - `find_similar_deals`: `{anchor_ids[], anchor_metrics:[{<SIMILARITY_FEATURES>...}], anchor_states[], financing, hard (same as search, all optional), exclude_ids[], limit}`.
  - `get_deal_details`: `{ids[] (1..10)}`.
  - `present_shortlist`: `{deals:[{underwriting_id, why, matched[], missed[]}] (1..6), summary}`.
- Shared candidate output per deal (search, similar and details): `{id, address, city, state, bedrooms, purchase_price, total_oop, tax_savings, tax_return_on_capital, m_cash_on_cash, y1_coc_incl_tax_savings, one_pct_ratio, down_payment_pct, interest_rate, interest_rate_is_stored: bool, score, breakdown, missing, turnkey, category_tags}` with money rounded to whole dollars and ratios to 4 dp.
- `search_deals` result: `{stage_counts: {pool, after_dedupe, dropped_unrecalculable, after_hard_filters, after_text_filter, after_exclusions}, candidates: [...]}`.

Behavior that the signatures leave open:
- Pool loading: `catalog.list_candidate_pool(statuses=ctx.pool_override.statuses if override else ["present_to_clients"], property_pending=override.property_pending if override else False, approved_from/to from override, down_payment_pct=input financing or ctx, interest_rate=...)`, then `dedupe_by_address`.
- Exclusions always include `ctx.already_shown_ids` plus `exclude_ids`. Under an eval `pool_override`, `already_shown_ids` are **not** excluded.
- Every id returned is added to `ctx.seen_ids`. `ctx.max_candidates_seen = max(..., len(candidates))`.
- `present_shortlist` validation, returning `is_error=True` with a list of reasons on failure:
  - every id is in `ctx.seen_ids`
  - no two ids share a normalized address
  - no id is in `ctx.already_shown_ids` (live only)
  - each id is still in the current pool at `ctx` financing
  - `3 <= len(deals) <= 6`, unless `ctx.max_candidates_seen < 3`, in which case `1..max_candidates_seen` is allowed

  On success:
  1. Recompute each deal's numbers via `catalog.list_candidate_pool` at `ctx` financing.
  2. Build `snapshot` = the shared candidate output plus `listing_url`, `video_walkthrough`, `loom_vid` (from `get_details`).
  3. Set `match_score` = that deal's score from the last search or similar call that returned it, else null.
  4. Write the recommendations with ranks 1..n in the given order.
  5. Set `ctx.shortlist_presented = True`.
  6. Emit `("shortlist", {"cards": [...], "summary": ...})`.
  7. Return `{"presented": n}`.
- Unknown tool name, or input failing Pydantic validation → `is_error=True`, `content={"error": "..."}`.

- [ ] **Step 1: Write failing tests** (`test_tools.py`) with a `FakeCatalog` holding ~8 `CatalogDeal`s (two sharing an address), an in-memory fake `RecommendationRepository`, and a `RunContext` with a recording `emit`:
  - `test_search_dedupes_and_reports_stage_counts`
  - `test_search_applies_hard_filters_and_exclusions_including_already_shown`
  - `test_search_text_filter_vs_boost`
  - `test_search_with_impossible_budget_returns_empty_candidates_with_counts` (Review Focus 2)
  - `test_search_uses_ctx_financing_when_input_omits_it` (assert the fake catalog got `down_payment_pct=Decimal("0.1")`)
  - `test_pool_override_widens_statuses_and_skips_already_shown_exclusion`
  - `test_update_profile_saves_version_sets_ctx_and_emits`
  - `test_present_shortlist_rejects_unseen_duplicate_and_already_shown_ids`
  - `test_present_shortlist_allows_fewer_than_three_only_when_searches_found_fewer` (Review Focus 2)
  - `test_present_shortlist_writes_snapshot_and_emits_cards`
  - `test_invalid_input_returns_error_outcome`
  - `test_tool_definitions_are_strict`: every definition has `"strict": True` and `input_schema.additionalProperties is False` at every object level.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/deal_recommendation/test_tools.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** `profile.py`, `context.py` and `tools.py`. Write `input_schema` dicts by hand rather than generating them from Pydantic, so they meet the strict-mode rules: every property listed in `required`, nullable fields as `["type","null"]`, `additionalProperties: false` on every object. Validate inputs with the Pydantic models before executing.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `uv run pytest tests/deal_recommendation/test_tools.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/deal_recommendation/agent tests/deal_recommendation/test_tools.py
git commit -m "feat(deal_recommendation): client profile, tools, and tool executor"
```

---

### Task 6: System prompt and agent loop (SDK Tool Runner)

**Files:**
- Modify: `pyproject.toml` / `uv.lock` (`uv add anthropic`)
- Modify: `app/core/config.py` (add `ANTHROPIC_API_KEY: str = ""`, `DEAL_REC_MODEL: str = "claude-sonnet-5-5"`, `DEAL_REC_EFFORT: str = "high"`, `DEAL_REC_MAX_TOOL_CALLS: int = 12`), `.env.example` (same keys, empty key)
- Create: `app/deal_recommendation/agent/prompt.py`, `agent/runner_tools.py`, `agent/loop.py`
- Test: `tests/deal_recommendation/test_loop.py`, `tests/deal_recommendation/test_prompt.py`

**How it works:** the Anthropic SDK's **Tool Runner** (`client.beta.messages.tool_runner(..., stream=True)`) does the looping. It calls Claude, runs whichever of our tool functions Claude asks for, feeds the results back, and repeats until Claude stops calling tools. Our code does four things around it:
1. Forward streamed text to the UI.
2. Save each turn to the database.
3. Stop runaway runs with a tool budget.
4. If Claude finishes without a shortlist or a question, restart the runner once with a nudge.

**Interfaces:**
- Consumes: `TOOL_DEFINITIONS`, `TOOL_PROGRESS_LABELS`, `ToolExecutor`, `ToolOutcome`, `RunContext` (Task 5); `ConversationRepository`, `RunRepository`, `RunUsage` (Task 4).
- Produces:
  ```python
  # prompt.py
  def build_system_prompt(tag_options: Mapping[str, Sequence[str]]) -> str
      # tag slugs sorted by set_code then slug, so the prefix is byte-stable and cacheable
  NUDGE_TEXT: str   # "Finish this turn: call present_shortlist with your best 3–6 deals, or ask the team member one clarifying question."
  BUDGET_TEXT: str  # "Tool budget reached. Call present_shortlist now with the best deals you have found."

  # runner_tools.py
  ToolHandler = Callable[[dict], Awaitable[str]]          # tool input -> JSON string result
  def build_tool_handlers(executor: ToolExecutor, ctx: RunContext, runs: RunRepository,
                          max_tool_calls: int) -> dict[str, ToolHandler]
  def to_sdk_tools(handlers: Mapping[str, ToolHandler]) -> list   # Tool Runner tool objects using TOOL_DEFINITIONS schemas
  class ToolBudgetExhausted(Exception): ...

  # loop.py
  @dataclass
  class LoopSettings:
      model: str; effort: str; max_tool_calls: int; max_tokens: int = 64000
  @dataclass
  class RunResult:
      status: str               # succeeded | failed | capped
      stop_reason: str | None; iterations: int; usage: RunUsage; error: str | None
  RunnerFactory = Callable[[list[dict], dict[str, ToolHandler]], Any]   # history, handlers -> async-iterable runner
  class AgentLoop:
      def __init__(self, client: Any, executor: ToolExecutor, session: AsyncSession,
                   conversations: ConversationRepository, runs: RunRepository,
                   settings: LoopSettings, system_prompt: str,
                   runner_factory: RunnerFactory | None = None): ...   # None -> SDK tool runner
      async def run(self, ctx: RunContext) -> RunResult
          # assumes the user message is already appended (Task 7 does that before creating the run)
  ```

**Behavior that the signatures leave open:**
- **Runner arguments** (default factory): `client.beta.messages.tool_runner(model=settings.model, max_tokens=64000, system=[{"type":"text","text":system_prompt}], tools=to_sdk_tools(handlers), messages=history, stream=True, thinking={"type":"adaptive"}, output_config={"effort": settings.effort}, cache_control={"type":"ephemeral"}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")`, using `AsyncAnthropic`.
- **SDK check first:** before writing the factory, read the installed SDK's tool-runner helpers (`.venv/lib/python3.12/site-packages/anthropic/lib/tools/`) or the SDK repo's helpers docs. You need three things from it:
  - how to give a runner tool an explicit `input_schema` plus `strict: True`, so our hand-written `TOOL_DEFINITIONS` are what gets sent
  - the async streaming iteration shape
  - whether `generate_tool_call_response()` is awaited
- **Tool handlers:** each handler does the following, then returns `json.dumps(outcome.content)`:
  1. Emit `tool_started {tool, label}`.
  2. Time and run `executor.execute`, turning exceptions into an error outcome.
  3. Write the `tool_calls` row.
  4. Emit `tool_finished {tool, summary: outcome.summary, is_error, duration_ms}`.

  An error outcome is raised so the runner marks the result `is_error`, or returned with an error key, whichever the SDK supports. Budget: once `max_tool_calls` calls have run, every tool except `present_shortlist` returns `BUDGET_TEXT` as an error without executing. At `max_tool_calls + 3` calls, the handler raises `ToolBudgetExhausted`.
- **Per streamed turn:**
  - Forward every `text` event as `text_delta {text}`.
  - Take the final message, add its usage to the run total, and keep the assistant content as `[b.to_dict() for b in message.content]`.
  - If it has tool calls, get `runner.generate_tool_call_response()` (this runs the tools), then save the assistant turn and the tool-result turn **together in one commit**.
  - Otherwise save the assistant turn alone.
  - On `refusal`, or on `max_tokens` with a tool call pending, save the assistant turn without running its tools and fail the run.
- **End of runner:** if no shortlist was presented, the final text doesn't end with `?`, and no nudge has been sent yet:
  1. Save a `system` message with `NUDGE_TEXT`.
  2. Start a fresh runner from the saved history. This is also how a `pause_turn` is resumed.
  3. Only one nudge per run.
- **Run status:**
  - `capped` on `ToolBudgetExhausted`.
  - `failed` on API errors or refusal, with the error stored and an `error {message}` event.
  - `succeeded` otherwise.

  Always call `finish_run` with usage and cost, then emit `run_finished {status, usage, cost_usd}`.

**System prompt** must cover every bullet in spec §5.2, plus:
- call `update_client_profile` before the first search, and again whenever the team member changes a preference
- resolve already-shown deals to ids via `search_deals` (city/text) and save them in `already_shown_ids`
- use `find_similar_deals` for deals the client reacted to positively
- quote numbers only from tool outputs, and say "at stored rate" when `interest_rate_is_stored`
- the co-host fee is display-only
- write a one-line note to the team member before each tool call saying what it's about to check, because the team sees the text stream live

- [ ] **Step 1: Write failing tests** with a fake `runner_factory`. It returns a fake runner whose async iteration yields scripted turns: text events plus a final message with `.content` blocks (each with `.type` and `.to_dict()`), `.stop_reason` and `.usage`. Its `generate_tool_call_response()` calls the real handlers it was given, for the turn's `tool_use` blocks. Tests:
  - `test_default_factory_request_shape`: patch `client.beta.messages.tool_runner` and record its kwargs. Expect `model == "claude-sonnet-5-5"`, `stream is True`, `thinking == {"type":"adaptive"}`, `output_config == {"effort":"high"}`, `cache_control == {"type":"ephemeral"}`, `"tool_choice" not in kwargs`, `fallbacks == "default"`, `betas == ["server-side-fallback-2026-07-01"]`, and five tools.
  - `test_turns_saved_with_tool_results_together`: script = [tool_use search_deals] → [tool_use present_shortlist] → [text]. Stored roles are `user, assistant, user, assistant, user, assistant`. Every `tool_use` id has a matching `tool_result` in the next row. Status `succeeded`.
  - `test_stream_events_in_order`: `text_delta` before `tool_started`, then `tool_finished` with its summary, then the next `text_delta`.
  - `test_nudges_once_when_no_shortlist_and_no_question`: exactly one `system` row equal to `NUDGE_TEXT`, and a second runner was created.
  - `test_clarifying_question_ends_run_without_nudge` (Review Focus 1)
  - `test_tool_budget_then_capped`: with `max_tool_calls=2`, the third search returns `BUDGET_TEXT` and status is `capped` after 5 calls.
  - `test_api_error_marks_failed_and_keeps_history_valid` (Review Focus 5): the runner raises `anthropic.APIStatusError` on turn 2. Status `failed`, an `error` event is emitted, and stored history has no unanswered `tool_use`.
  - `test_refusal_marks_failed`
  - `test_usage_accumulates_across_turns`
  - `test_prompt.py::test_prompt_is_deterministic_and_lists_slugs`

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/deal_recommendation/test_loop.py tests/deal_recommendation/test_prompt.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** `uv add anthropic`, the config fields, `prompt.py`, `runner_tools.py` and `loop.py`. Ask the user for the Anthropic API key and add it to `.env` only.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `uv run pytest tests/deal_recommendation -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock app/core/config.py .env.example app/deal_recommendation/agent tests/deal_recommendation
git commit -m "feat(deal_recommendation): system prompt and Tool Runner agent loop"
```

---

### Task 7: Run manager, SSE API, router

**Files:**
- Create: `app/deal_recommendation/schemas/__init__.py`, `schemas/api.py`
- Create: `app/deal_recommendation/services/run_manager.py`, `services/conversation_service.py`
- Create: `app/deal_recommendation/controllers/__init__.py`, `controllers/conversation_controller.py`
- Create: `app/deal_recommendation/router.py`
- Modify: `app/__init__.py` (include the router next to the others)
- Test: `tests/deal_recommendation/test_api.py`, `tests/deal_recommendation/test_run_manager.py`

**Interfaces:**
- Consumes: everything from Tasks 1, 4, 5 and 6; `AsyncSessionLocal` from `app.core.database`; `ReferenceDataService` from `app.core.reference_data` (for prompt slugs, `domain="iron_bank"`).
- Produces:
  ```python
  # run_manager.py
  class ConversationBusy(Exception): ...
  class RunManager:
      def __init__(self, session_factory=AsyncSessionLocal, client_factory=lambda: AsyncAnthropic(api_key=...)): ...
      async def start(self, *, conversation_id: UUID, text: str, user_id: int | None,
                      pool_override: PoolOverride | None = None) -> AsyncIterator[str]
          # raises ConversationBusy before yielding if has_active_run or an in-process task exists
      async def run_to_completion(self, *, conversation_id: UUID, text: str, user_id: int | None,
                                  pool_override: PoolOverride | None = None) -> RunResult   # used by eval
  run_manager = RunManager()   # module-level singleton, overridable in tests via dependency
  def format_sse(event: str, data: dict) -> str   # "event: {event}\ndata: {json}\n\n"
  ```
- Endpoints (`router = APIRouter(prefix="/deal-recommendation", tags=["deal_recommendation"])`):
  - `POST /conversations` body `{title?: str}` → 201 `{id, title, created_at}`
  - `GET /conversations` → `{items: [{id, title, updated_at}]}`, newest first
  - `GET /conversations/{id}` → `{id, title, turns: [...]}`. Each turn is `{user_text, run: {id, status, cost_usd} | null, assistant_text, profile: {...} | null, cards: [...]}`. It's built from `list_messages` (user text rows, and assistant `text` blocks of the run's final assistant row), `list_runs`, `list_profiles` and `list_for_conversation`, grouped by run. 404 if missing.
  - `POST /conversations/{id}/messages` body `{text: str (1..50000 chars)}` → `StreamingResponse(media_type="text/event-stream")`. 409 `{"detail": "A run is already in progress for this conversation."}` when busy, 404 when missing.
  - `GET /runs/{id}/trace` → `{run: {...all agent_runs columns}, tool_calls: [{seq, tool_name, input, output, is_error, duration_ms}]}`. 404 if missing.

Run manager behavior:
1. Open a dedicated session from `session_factory`, not the request session.
2. Append the user message and create the run (commit).
3. Build the `RunContext`, with financing and already-shown ids from `latest_profile`.
4. Start `asyncio.create_task(loop.run(ctx))` with `emit` putting `(event, data)` on an `asyncio.Queue`. The task is held in `self._tasks[conversation_id]` and removed on completion.
5. The SSE generator yields `run_started`, then queue items until `run_finished` or `error`.
6. If the client disconnects, the generator is cancelled but the **task keeps running**: never cancel the task from the generator.

Default title = first 60 chars of the first user message's first line when the conversation has no title.

- [ ] **Step 1: Write failing tests:**
  - `test_api.py` (pattern: `tests/markets/test_markets_list_api.py`, override `get_current_user` and the controller dependency):
    - `test_create_and_list_conversations`
    - `test_get_missing_conversation_404`
    - `test_post_message_streams_sse_events` (fake controller yields `format_sse` strings; assert `content-type` starts with `text/event-stream` and the body contains `event: run_started`)
    - `test_post_message_when_busy_returns_409` (Review Focus 3)
    - `test_message_text_validation` (empty → 422)
    - `test_trace_404`
  - `test_run_manager.py`, with fake session factory, fake loop and in-memory repos:
    - `test_disconnect_does_not_cancel_run` (Review Focus 4): consume only the first event, close the generator, await the task, and assert `finish_run` was called with `succeeded`.
    - `test_busy_when_task_running`
    - `test_stale_running_run_does_not_block` (Review Focus 3: a `has_active_run` with a run started 20 min ago → not busy)
    - `test_format_sse`

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/deal_recommendation/test_api.py tests/deal_recommendation/test_run_manager.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement** the schemas, run manager, conversation service, controller and router, and register the router in `app/__init__.py`.

- [ ] **Step 4: Run the full test suite and a live smoke test**

Run: `uv run pytest -q`
Expected: all PASS.

Then start the server with `uvicorn main:app --reload` and issue an API key: `uv run python scripts/issue_api_key.py --user-id <the user's id> --name deal-recommendation-fe` (ask the user which user id). Create a conversation with `curl -X POST -H "X-ADUS-API-KEY: $KEY" localhost:8000/deal-recommendation/conversations`, then stream: `curl -N -X POST -H "X-ADUS-API-KEY: $KEY" -H "Content-Type: application/json" -d '{"text": "<Anna summary from the eval cases file>"}' localhost:8000/deal-recommendation/conversations/<id>/messages`.
Expected: `run_started`, `text_delta` events, `tool_started`/`tool_finished` pairs, a `profile` event, a `shortlist` event with 3–6 cards, and `run_finished` with status `succeeded`. Rows exist in all six tables. This spends real API money (a few dollars at most); tell the user before running it.

- [ ] **Step 5: Commit**

```bash
git add app/deal_recommendation app/__init__.py tests/deal_recommendation
git commit -m "feat(deal_recommendation): run manager and SSE conversation API"
```

---

### Task 8: Eval harness

**Files:**
- Create: `scripts/fixtures/deal_recommendation_eval_cases.json` (copy of `docs/superpowers/plans/2026-10-17-deal-recommendation-v1-eval-cases.json`)
- Create: `scripts/eval_deal_recommendation.py`, `app/deal_recommendation/services/eval_scoring.py`
- Test: `tests/deal_recommendation/test_eval_scoring.py`

**Interfaces:**
- Consumes: `run_manager.run_to_completion` and `PoolOverride` (Tasks 5 and 7), `normalize_address` (Task 2), the repositories (Task 4), `DealCatalogService.list_candidate_pool` (for the pool size).
- Produces:
  ```python
  # eval_scoring.py
  @dataclass
  class CaseScore:
      case: str; pool_size: int; sent_in_pool: int
      shortlist_hits: int; shortlist_size: int
      top20_hits: int; random_top20: float; random_shortlist: float
  def score_case(*, case_name: str, sent_addresses: Sequence[str], pool: Sequence[CatalogDeal],
                 shortlist_ids: Sequence[int], last_search_ids: Sequence[int]) -> CaseScore
      # hits by normalize_address; sent_in_pool = sent addresses present in pool;
      # random_top20 = min(20, pool_size) * sent_in_pool / pool_size; random_shortlist likewise with shortlist_size
  ```
- CLI: `uv run python scripts/eval_deal_recommendation.py [--case NAME] [--yes]`.
  1. For each case, create a conversation titled `eval:<case>:<timestamp>`.
  2. Call `run_to_completion` with `PoolOverride(statuses=["present_to_clients","client_under_contract"], approved_from, approved_to, property_pending=None)`.
  3. Read the shortlist ids from the recommendations, and `last_search_ids` from the last `search_deals` or `find_similar_deals` tool call output in the trace.
  4. Print a table of `CaseScore`s, plus the run id, cost and conversation id for opening in the UI.

  Without `--yes` it prints "This runs N real agent runs (~$X estimated) — continue? [y/N]" (estimate $2 per case).

- [ ] **Step 1: Write failing tests:**
  - `test_score_case_counts_hits_by_address_not_id`: a sent address whose pool twin has a different id still counts.
  - `test_random_baselines`: pool 75, sent_in_pool 13 → `random_top20 ≈ 3.47`.
  - `test_sent_addresses_missing_from_pool_reduce_sent_in_pool`.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `uv run pytest tests/deal_recommendation/test_eval_scoring.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** `eval_scoring.py` and the script.

- [ ] **Step 4: Run the tests, then the eval with user approval**

Run: `uv run pytest tests/deal_recommendation/test_eval_scoring.py -v` → PASS.
Then ask the user, and run `uv run python scripts/eval_deal_recommendation.py --yes`.
Expected: both cases complete. Report the table to the user as-is. The spec's demo bar is shortlist hits above `random_shortlist` on both cases. If a case misses the bar, report it; do not tune the prompt in this task.

- [ ] **Step 5: Commit**

```bash
# *.json is gitignored repo-wide (credential files), so the fixture needs -f
git add -f scripts/fixtures/deal_recommendation_eval_cases.json
git add scripts/eval_deal_recommendation.py app/deal_recommendation/services/eval_scoring.py tests/deal_recommendation/test_eval_scoring.py
git commit -m "feat(deal_recommendation): eval harness for the two real client cases"
```

---

### Task 9: Frontend scaffold, server proxy, SSE client

**Files (new repo `/Users/tarifulislam/Documents/str-projects/adus-project/deal-recommendation-fe`):**
- Create via `npx create-next-app@latest deal-recommendation-fe --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm`
- Create: `.env.local.example` (`ADUS_API_BASE_URL=http://localhost:8000`, `ADUS_API_KEY=`), `.env.local` (real values, gitignored)
- Create: `lib/adus.ts`, `lib/sse.ts`, `lib/types.ts`
- Create: `app/api/conversations/route.ts`, `app/api/conversations/[id]/route.ts`, `app/api/conversations/[id]/messages/route.ts`, `app/api/runs/[id]/trace/route.ts`
- Test: `lib/sse.test.ts` (vitest; add `vitest` dev dep and `"test": "vitest run"` script)

**Interfaces:**
- Produces:
  ```ts
  // lib/adus.ts — server-only (import "server-only")
  export async function adusFetch(path: string, init?: RequestInit): Promise<Response>
    // prefixes ADUS_API_BASE_URL + "/deal-recommendation", sets X-ADUS-API-KEY, never caches
  // lib/sse.ts
  export type SseEvent = { event: string; data: unknown };
  export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent>
  // lib/types.ts — TS mirrors of the API shapes in Task 7: Conversation, Turn, DealCard (= snapshot + rank, why, matched, missed, match_score), ClientProfile, RunTrace
  ```
- Route handlers forward method, JSON body and status, and pass the upstream `Response.body` through unchanged for the messages route, with `content-type: text/event-stream`, `cache-control: no-cache`, and `export const dynamic = "force-dynamic"`.

- [ ] **Step 1: Write failing tests** `lib/sse.test.ts`:
  - parses two events split across arbitrary chunk boundaries
  - ignores comment lines (`:`)
  - JSON-parses `data`
  - handles `\r\n` line endings

- [ ] **Step 2: Run tests and confirm they fail**

Run: `npm test`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement** `lib/*` and the route handlers.

- [ ] **Step 4: Run tests and smoke-test the proxy**

Run: `npm test` → PASS. With adus-be running, `npm run dev`, then `curl -s localhost:3000/api/conversations` → JSON list from adus-be. Confirm in the browser devtools Network tab that no request carries `X-ADUS-API-KEY`.

- [ ] **Step 5: Commit**

```bash
git init -b main 2>/dev/null; git add -A && git commit -m "feat: scaffold, adus-be proxy, SSE parser"
```

---

### Task 10: Chat UI

**Files:**
- Create: `lib/useDealChat.ts`, `components/ConversationList.tsx`, `components/ChatThread.tsx`, `components/UserMessage.tsx`, `components/AssistantTurn.tsx`, `components/DealCard.tsx`, `components/ProfileLine.tsx`, `components/TracePanel.tsx`
- Modify: `app/page.tsx`, `app/layout.tsx` (title "Deal Recommendations")
- Add: shadcn/ui `button`, `card`, `badge`, `textarea`, `sheet` (`npx shadcn@latest init` then `add`), and `react-markdown` for assistant text

**Interfaces:**
- Consumes: `/api/*` routes, `parseSse`, `lib/types.ts` (Task 9).
- Produces:
  ```ts
  export function useDealChat(conversationId: string | null): {
    turns: Turn[]; liveTurn: LiveTurn | null; sending: boolean; error: string | null;
    send(text: string): Promise<void>;  // POSTs, consumes SSE into liveTurn, then refetches the conversation
  }
  // LiveTurn = { items: Array<{kind:"text"; text:string} | {kind:"tool"; tool:string; label:string; status:"running"|"done"|"error"; summary?:string; duration_ms?:number}>;
  //              profile: ClientProfile | null; cards: DealCard[]; status: string | null }
  ```

UI rules (spec §9, layout B):
- **Left column:** conversation list (newest first) with a "New conversation" button.
- **User message:** a pasted text longer than 400 chars is collapsed to its first 3 lines, with "Show all".
- **Assistant turn, in order:**
  - **the live stream, in arrival order:** the assistant's text renders token by token as `text_delta` events arrive. Each tool call appears inline as a step row: a spinner and the label on `tool_started`, then a check (or a red mark) with the summary and duration on `tool_finished`. After the run, saved turns show the same text, with the tool steps collapsed under "N steps" (rebuilt from the trace).
  - `ProfileLine`, a one-line summary: budget max OOP, down payment %, top 3 goals by importance, preferred states, already-shown count
  - the markdown text
  - the cards
  - a footer with run status, cost (`$0.00`) and a "View trace" button
- **`DealCard`:**
  - rank and address, city/state, beds
  - `match_score` badge
  - a numbers row: OOP, Y1 tax savings, tax return on capital %, CoC %, 1% ratio %
  - the line "at {down_payment_pct}% down", plus "· stored interest rate" when `interest_rate_is_stored`
  - the `why`
  - green chips for `matched` and red chips for `missed`
  - links (listing, video, loom) when present
- **`TracePanel`** (sheet): one row per tool call with tool name, duration and error flag. Expanding a row shows pretty-printed input and output JSON.
- **Composer:** a textarea with Send disabled while `sending`. A 409 shows "A run is already in progress for this conversation."

- [ ] **Step 1: Write a failing test** `lib/useDealChat.test.ts` (vitest + `@testing-library/react`, mocking `fetch` with an SSE body): after `send()`, `liveTurn.cards.length === 2`, `liveTurn.profile` is set, `liveTurn.items` interleaves text and tool steps in arrival order (a tool step flips from `running` to `done` with its summary), and a 409 response sets `error` to the exact message above.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `npm test`
Expected: FAIL.

- [ ] **Step 3: Implement** the hook, the components and the page.

- [ ] **Step 4: Run tests and verify in the browser**

Run: `npm test` → PASS. Then, with adus-be and `npm run dev` running, open `localhost:3000` in the browser pane:
1. Paste the Anna summary from the eval cases file.
2. Confirm the text streams in live, tool steps appear and complete as they run, and check the profile line, 3–6 cards with numbers at 10% down, and that the trace opens.
3. Send "more cash flow, avoid two deals in the same market".
4. Confirm the new turn and that the earlier turn is still visible after a reload.

This spends real API money; tell the user first.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: chat thread UI with deal cards and run trace"
```
