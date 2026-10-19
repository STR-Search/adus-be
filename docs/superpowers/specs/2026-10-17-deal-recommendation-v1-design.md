# Deal Recommendation v1 — Design

Date: 2026-10-17
Status: draft for approval

## 1. Intent

After an onboarding call, an acquisition team member reads the Fathom summary
and hand-picks deals from the ~900 underwritings marked `present_to_clients`
to send the client. v1 is a chat tool that does that first pass: paste the
Fathom summary, get 4–5 recommended deals with a plain-English reason for each,
then refine by chatting ("more cash flow", "drop the Smokies duplicate",
"anything with pickleball under 350?").

Why now, and what v1 is for:

- **A demo for leadership** to react to. Not a production system.
- **A learning build.** The team wants to understand every technical detail of
  how it works before making it robust. Prefer code that is small, explicit and
  traceable over clever or abstracted code. Every agent decision must be
  inspectable after the fact.

Later (not v1): study how the acquisition team actually picks deals, then try
different approaches. v1 must make that comparison possible (see §10 eval).

## 2. Goals, non-goals, anti-goals

Goals
- Paste a Fathom summary → streamed reply with what the agent understood about
  the client and 4–5 deal cards, each with match score, key numbers, matched vs
  missed preferences, and "why the AI chose this deal".
- Follow-up messages refine the list in the same conversation.
- Conversations, every tool call, and every recommendation are persisted and
  reviewable.
- A repeatable eval against the two real client cases we have.

Non-goals (v1)
- Login / per-user accounts in the frontend.
- Sending lists to clients, client portal integration, saving "final" lists.
- Feedback/rating capture (done manually by the team).
- Per-client memory across separate calls.
- Fathom API integration (summary is pasted).
- Semantic/vector search; backfilling the empty deal tags.
- Keep/Swap/Remove buttons (chat only).

Anti-goals (would make v1 a failure even if it "works")
- Recommending a deal that is not currently `present_to_clients` (outside the
  eval harness).
- Recommending the same property twice (duplicate underwritings exist, §4).
- Numbers on a card that don't match what the underwriting says at the
  client's financing terms (e.g. showing 20%-down OOP to a 10%-down client).
- The LLM inventing deals, IDs, or numbers. All numbers come from our code.
- An agent run nobody can explain afterwards.

## 3. Architecture

```
Next.js app (new project)                adus-be (existing FastAPI)
 ┌───────────────────────────┐          ┌──────────────────────────────────────┐
 │ Chat page (browser)       │          │ app/deal_recommendation/  (new)       │
 │   │ fetch /api/...        │          │   router → controller → service       │
 │   ▼                       │  HTTPS   │   agent/ (Claude tool runner + tools) │
 │ Next route handlers ──────┼─────────▶│   repositories (deal_recommendation.*)│
 │  (adds X-ADUS-API-KEY,    │   SSE    │           │                           │
 │   proxies SSE stream)     │◀─────────┤           ▼ read-only, one seam        │
 └───────────────────────────┘          │ app/iron_bank/services/                │
                                        │   deal_catalog_service.py (new facade) │
                                        └──────────────────────────────────────┘
                                                    │
                                     Postgres: iron_bank.* (read), deal_recommendation.* (rw)
                                                    │
                                              Claude API (claude-sonnet-5-5)
```

### 3.1 Backend: new domain in adus-be (decided)

`app/deal_recommendation/` following the existing domain layout
(models / schemas / repositories / services / controllers / router), router
registered in `app/__init__.py`.

New DB schema `deal_recommendation` with its own Alembic branch (the sixth).
Update adus-be `CLAUDE.md`: managed schemas list, Alembic branches list,
domain table.

### 3.2 The one cross-domain exception (decided)

adus-be's rule is "never import between domains". v1 adds **one documented,
read-only exception**: `deal_recommendation` may import exactly one module,
`app/iron_bank/services/deal_catalog_service.py`, a new read-only facade owned
by iron_bank. Nothing else from iron_bank (or any other domain) is imported.
Document this in adus-be `CLAUDE.md`.

The facade composes existing iron_bank code (`GetUnderwritingService`,
`SimulateUnderwritingsService`, `UnderwritingCalculator`, repositories) and adds
the few reads the agent needs that don't exist yet. It never writes. It returns
plain Pydantic/dataclass DTOs, never ORM objects. Its surface (exact signatures
are the builder's call):

- `list_candidate_pool(statuses, approved_between=None, down_payment_pct=None, interest_rate=None)`
  → all candidate deals with the fields in §6.2, financing-simulated when
  overrides are given (reuse `SimulateUnderwritingsService` semantics; tax
  values don't change with financing).
- `text_search(ids, query)` → which of the given deals match a free-text query
  across `deal_pitch`, `note`, `uw_details.analyst_notes`,
  `uw_details.construction_and_design_notes`, and `uw_optimization_items`
  (`category`, `spec`, `notes`). Simple `ILIKE` per term is fine for v1.
- `get_details(ids)` → full context per deal: the pool fields plus pitch,
  notes, analyst notes, construction notes, optimization items, comp-set
  amenity flags, `listing_url`, `video_walkthrough`, `loom_vid`, market name.

### 3.3 Frontend: new Next.js project (decided)

Separate project, not adus-dashboard. My call: sibling folder
`adus-project/deal-recommendation-fe`, Next.js App Router + TypeScript +
Tailwind + shadcn/ui, Vercel AI SDK UI (`useChat`) for the chat thread — or a
small custom SSE hook if the AI SDK's stream protocol fights the custom deal-card
parts (builder's call, note the choice in the README).

### 3.4 Auth (decided: no login screen)

- The browser only calls the Next.js app's own route handlers.
- Those handlers add `X-ADUS-API-KEY` from a server-only env var and proxy to
  adus-be, streaming SSE through unchanged. The key never reaches the browser.
- adus-be's global auth guard stays on; deal_recommendation routes are **not**
  exempted. Conversations are attributed to the API key's user.
- v1 runs locally for the demo. No shared URL, no passcode (my call; add a
  shared passcode if it ever gets deployed).
- Issue the key with `uv run python scripts/issue_api_key.py --user-id <id> --name deal-recommendation-fe`.

## 4. Data facts the design rests on

From read-only queries on 2026-10-17 (dev DB):

| Fact | Consequence |
|---|---|
| 931 `present_to_clients` rows, 898 distinct addresses | Dedupe by normalized address; the same property is often a separate underwriting (not a version), e.g. 674 Glasco Tpk has 3 rows with OOP $104k–$239k. |
| Tags nearly empty in that pool: `turnkey` 32, `tax_efficient` 0, `execution_type` 1, `market_type` 140, `deal_score` 0 | Scoring cannot rely on tags. Use numbers + free text. Tags are a bonus when present. |
| `tax_savings` 707/931, `analyst_notes` 678, `deal_pitch` 115 | Free text exists for most deals. |
| 224 legacy rows have no `purchase_details`, no `forecasted_revenue` and no tax savings | They can't be recalculated at the client's terms and have no tax numbers: excluded from the pool (§6.1). Pool ≈ 707. None of the eval's sent deals are in this group. |
| Stored down payment: 10% → 682, 20% → 22, 25% → 2, missing → 215 | Recalculate at the client's down payment. Example: Austin stored at 20% (OOP $398k) vs quoted at 10% (~$223k). |
| Sent lists span ~2 months of approvals (Feb 23 – May 13 2026); many sent deals are now `client_under_contract` | Eval must use an "as-of" candidate pool (§10). |
| Amit's sent deals skew to cash flow (1% rule, CoC) and Florida (40% vs 15% of pool), below median on tax savings, despite the summary saying tax and profit equally | Reactions to specific deals on the call ("Blue Ridge cash flow too low", "Savannah very appealing") are strong signals; capture them in the profile. Weights must be per client. |
| Simple percentile scoring with the right weights puts 7 of 13 of Amit's sent deals in the top 20 of a 75-deal as-of pool (random ≈ 3.5) | Deterministic scoring + per-client weights is a sound base for the agent's search tool. |

## 5. The agent

### 5.1 Shape

One Claude conversation per chat thread, run as a tool-use loop with the
Anthropic Python SDK Tool Runner (`client.beta.messages.tool_runner` +
`@beta_tool`). Each user message starts one **run**: the loop calls tools until
the agent calls `present_shortlist` or ends its turn.

- Model `claude-sonnet-5-5` with effort `high` (decided), adaptive thinking,
  streaming. Both configurable via env.
- The SDK Tool Runner does the looping (decided): it calls Claude, runs the
  tools Claude asks for, feeds results back, and repeats. Our code wraps it to
  stream text to the UI, save each turn, enforce the tool budget, and nudge
  once.
- Server-side refusal fallback enabled (`fallbacks: "default"` with the
  `server-side-fallback-2026-07-01` beta), per Anthropic's current guidance
  for this model.
- Cap: 12 tool calls per run (configurable). On hitting the cap, the agent is
  told to present the best list it has.
- Forced `tool_choice` is not supported on this model. Use `auto`, mark tools
  `strict: true`, and instruct in the system prompt that every run ends with
  `present_shortlist` (or a clarifying question if the notes are unusable).
  If a run ends without a shortlist and without a question, the backend sends
  one follow-up nudge; if that also fails, the run ends with the text reply.
- Prompt caching on the system prompt + tool definitions (stable prefix).
- Anthropic API key in adus-be `.env` as `ANTHROPIC_API_KEY` (user provides).

### 5.2 System prompt contents (builder writes the prose)

- Role: help the acquisition team shortlist deals for a client from a call
  summary; the team member is the reader, not the client.
- How the domain works, briefly: OOP, tax savings via bonus depreciation
  (depends on purchase price, not down payment), cash-on-cash, the 1% rule,
  turnkey vs value-add.
- Allowed slug values for the tag fields (loaded from `reference.enum_options`
  at startup, sorted, so the prefix stays cacheable), and a note that most
  deals have no tags.
- Rules: only recommend deals returned by tools; never compute financial
  numbers yourself; recalculate at the client's down payment; avoid two deals
  in the same micro-market unless asked; explain trade-offs honestly.
- When stated priorities and reactions to specific deals conflict, say so in
  the reply and cover both in the shortlist (my call, since the Amit question
  in §11 is open).
- Process: first record the profile (`update_client_profile`), then search,
  look at details for finalists, then present.

### 5.3 Tools (v1: five)

All tool inputs are validated (strict schemas + Pydantic). All tool outputs are
JSON. Every call is logged to `tool_calls` (§7).

1. **`update_client_profile(profile)`**
   Agent writes what it understood (schema §5.4). Saved as a new
   `client_profiles` version; streamed to the UI as the "Read from notes" line.
   On follow-ups the agent sends the full updated profile.

2. **`search_deals(...)`** — the core tool. Inputs:
   - `financing`: `down_payment_pct`, optional `interest_rate`. When the
     client gave no rate, each deal keeps its stored rate (current simulation
     behaviour); the card says so.
   - `hard`: `max_oop`, optional `min_oop`, `states_include`, `states_exclude`,
     `min_bedrooms`, `max_bedrooms`, `max_purchase_price`, `min_purchase_price`
   - `weights`: 0–5 per metric (§6.2) plus `state_preference` (list of states
     with a bonus weight) and optional tag preferences
   - `text_query` (optional), `text_mode`: `filter` | `boost`
   - `exclude_ids`, `limit` (default 15, max 30)

   `exclude_ids` is how "already shown" works: the agent resolves the
   profile's `already_shown` labels to IDs with `search_deals` (text/city) and
   stores them in `already_shown_ids`; the backend then also excludes
   `already_shown_ids` from the latest profile automatically, and
   `present_shortlist` rejects them unless the user asked for them back.

   Steps in code: load pool (current `present_to_clients`, `property_pending`
   false, dedupe by address) at the given financing → hard filters → text
   filter/boost → score (§6) → return ranked candidates with the score
   breakdown and the numbers shown on cards. Returns the count before/after
   each filter stage so the agent can see why a search came back thin.

3. **`find_similar_deals(anchor_ids?, anchor_metrics?, financing, hard?, exclude_ids, limit)`**
   Deals that look like ones the client liked. Anchors are deal IDs (found via
   `search_deals`) or explicit metrics when the liked deal isn't in the DB
   (e.g. "Savannah 6-bed, OOP ~$212k, tax ~$155k"). Similarity = distance on
   percentile-normalized metrics (purchase price, OOP, bedrooms, tax return on
   capital, CoC, 1% rule) + same-state bonus. Same pool rules as search.

4. **`get_deal_details(ids)`** (max 10 per call)
   Full context from the facade for finalists, at the run's financing terms.

5. **`present_shortlist(deals, summary)`**
   `deals`: 3–6 items of `{underwriting_id, why, matched[], missed[]}`;
   `summary`: one short paragraph. Backend validates every ID was returned by a
   search/similar/details call **in this run**, is in the current pool, and is
   not a duplicate address. On failure it returns an error result and the agent
   retries. On success it writes `recommendations` rows with a snapshot of the
   numbers (computed by our code, at the run's financing) and streams the cards.

Dropped from earlier drafts: `get_allowed_values` (slugs live in the system
prompt), `recalculate_for_client` (folded into `financing`), `get_market_info`
(market name rides on details; market notes deferred).

### 5.4 Client profile (JSON, Pydantic-validated)

```json
{
  "client_label": "Rav & Anna",
  "call_date": "2026-03-27",
  "goals": [
    {"metric": "tax_savings", "importance": 5, "quote": "Maximize year-one tax savings..."},
    {"metric": "cash_on_cash", "importance": 3, "quote": "secondary focus on cash flow"}
  ],
  "budget": {"target_oop": 400000, "max_oop": 400000, "quote": "..."},
  "financing": {"down_payment_pct": 0.10, "interest_rate": null, "cohost_fee_pct": 0.12},
  "location": {"preferred_states": [], "excluded_states": [], "notes": "open to all markets", "quote": "..."},
  "property": {"turnkey_preference": "preferred", "value_add_ok": true, "amenities_wanted": ["pickleball"], "bedrooms_min": null},
  "benchmarks": [{"name": "one_pct_rule", "quote": "..."}],
  "deal_reactions": [
    {"label": "Austin, TX turnkey", "underwriting_id": 743, "sentiment": "positive", "reason": "proven income, tax efficient", "quote": "..."}
  ],
  "already_shown": ["Panama City Beach FL", "Austin TX", "Galena IL"],
  "already_shown_ids": [743, 818, 1060],
  "conflicts": ["..."],
  "open_questions": ["..."]
}
```

`cohost_fee_pct` is recorded but **display-only in v1**: the calculator has
no fee override, so numbers use each underwriting's stored fees and the card
says so. Making it affect the math is a later iron_bank change.

Every extracted item carries the quote it came from. `underwriting_id` on a
reaction is filled only if the agent resolved it via a tool.

## 6. Scoring (deterministic, in Python)

### 6.1 Pool
Current `present_to_clients`, `property_pending = false`, **recalculable**
(has `purchase_details` and `forecasted_revenue`; rows the simulation would
mark `simulated=False` are dropped, never shown with stored-terms numbers, and
the dropped count is reported in the `search_deals` stage counts), deduped by
normalized address (lowercase, strip unit/punctuation/"MLS…|Zillow" suffixes;
keep the row with the latest `deal_approved`, then highest `id`). Exact
normalization rules: builder's call, with unit tests from the real duplicates
in §4.

### 6.2 Metrics (all computed by our code, at the run's financing)
- `total_oop`, `purchase_price`, `bedrooms`, `state`, `city`
- `tax_savings` (from `uw_taxes`)
- `tax_return_on_capital` = `tax_savings / total_oop`
- `m_cash_on_cash` (and l/h for display)
- `y1_coc_incl_tax_savings`
- `one_pct_ratio` = `(mid_gross_revenue / 12) / purchase_price`
- tag flags when present

### 6.3 Score
Percentile-normalize each weighted metric within the post-filter pool; score =
Σ(weight × percentile) + state bonus + tag bonus + text boost, scaled to
0–100. Missing values score as the pool's 25th percentile (my call — penalize
but don't exclude) and are listed in the breakdown as "missing". Return the
per-component breakdown so the agent and the trace can explain the rank.

## 7. Database: schema `deal_recommendation`

```
conversations
  id uuid pk, title text, created_by_user_id int (users.users.id, set null),
  model text, status text, created_at, updated_at

messages                       -- exact Claude history, append-only
  id bigserial pk, conversation_id uuid fk cascade, seq int,
  role text check ('user','assistant'),
  content jsonb                -- raw content blocks incl. thinking, tool_use, tool_result
  created_at
  unique (conversation_id, seq)

agent_runs                     -- one per user message
  id uuid pk, conversation_id fk, user_message_id fk messages,
  model text, effort text, status text ('running','succeeded','failed','capped'),
  stop_reason text, iterations int,
  input_tokens int, output_tokens int, cache_read_tokens int, cache_write_tokens int,
  cost_usd numeric(10,4), error text, started_at, finished_at

tool_calls
  id bigserial pk, run_id fk cascade, seq int, tool_use_id text, tool_name text,
  input jsonb, output jsonb, is_error bool, duration_ms int, created_at

client_profiles
  id bigserial pk, conversation_id fk, run_id fk, version int, profile jsonb, created_at
  unique (conversation_id, version)

recommendations
  id bigserial pk, run_id fk, conversation_id fk, rank int,
  underwriting_id int        -- no FK to iron_bank (other domain)
  match_score numeric(5,2), why text, matched text[], missed text[],
  snapshot jsonb             -- address, city/state, beds, price, OOP, tax, ratios, links, at run financing
  created_at
```

Rules:
- `messages.content` stores exactly what was sent to / received from Claude,
  never rewritten. Continuing a conversation = load rows in `seq` order and
  send them. This is required for thinking-block replay on current models.
- The UI renders from `recommendations` + `client_profiles` + text, never by
  parsing raw blocks.
- No feedback table (decided).

## 8. API (adus-be)

Prefix `/deal-recommendation` (builder may match the existing prefix style).

- `POST /conversations` → `{id}` (optional title)
- `GET /conversations` → list (id, title, updated_at), newest first
- `GET /conversations/{id}` → turns for display: user texts, assistant texts,
  profile versions, recommendation sets per run, run status
- `POST /conversations/{id}/messages` `{text}` → **SSE stream** for one run.
  Event types (names are builder's call):
  - `run_started` `{run_id}`
  - `text_delta` `{text}` — the agent's reply, token by token
  - `tool_started` `{tool, label}` — e.g. "Searching deals at 10% down…"
  - `tool_finished` `{tool, summary, is_error, duration_ms}` — e.g. "42 candidates (707 in pool → 120 after filters)"
  - `profile` `{profile, version}`
  - `shortlist` `{cards[], summary}`
  - `run_finished` `{status, usage, cost_usd}`
  - `error` `{message}`
- `GET /runs/{id}/trace` → run + ordered tool calls (inputs/outputs) — the
  "why did it pick these" debugging view.

One run at a time per conversation (reject a second POST while running).
If the client disconnects mid-stream, the run still completes and persists.

## 9. Frontend (new Next.js project)

Single chat-thread page, layout B from brainstorming:

- Left: conversation list + "New conversation".
- Thread: user message bubbles (pasted summaries collapsed to a preview);
  assistant turns stream live (decided): text appears token by token, and
  each tool call shows as an inline step that goes from running to done with
  its one-line result; after the run the steps collapse under "N steps".
  Assistant turns show the "Read from notes"
  line (from `profile`), the text reply, and the deal cards.
- Deal card: rank, address + city/state, beds, match score, OOP / Y1 tax
  savings / tax return on capital / CoC / 1% ratio at the client's financing,
  the "why", matched chips and missed chips, links (listing, video, loom).
- "View trace" link per run opening the `/runs/{id}/trace` data in a simple
  readable panel (tool name, inputs, summarized outputs, duration).
- Route handlers under `app/api/...` proxy to adus-be with the API key.

Visual polish: builder's call; keep it clean and readable for a leadership demo.

## 10. Eval harness

`scripts/eval_deal_recommendation.py` in adus-be plus a fixtures file with the
two cases:

| Case | Summary | Sent deals (found in iron_bank) | As-of pool |
|---|---|---|---|
| Rav & Anna (call 2026-03-27) | Onboarding Call with Anna | ids 743, 850, 1034, 1065, 1073, 981, 1165, 983, 818, 1703 | approvals 2026-02-15 → 2026-05-20 |
| Amit & Radhika (call 2026-03-25) | Onboarding Call with Amit | ids 1324, 1121, 1738, 1151, 1018, 1126, 1119, 1056, 943, 1003, 857, 696, 817, 888, 1033, 1146, 952 | approvals 2026-02-15 → 2026-05-20 |

(Grand Lagoon Shores, Penrose Dr, and 12671 115th St are not in iron_bank and
are excluded. The full summaries go in the fixtures file. The builder should
re-verify the ID mapping, especially duplicates such as Galena 818/1060 and
Fort Lauderdale 946/1324.)

- The harness runs the real agent with an **eval-only pool override**:
  statuses `present_to_clients` + `client_under_contract`, approved within the
  window, and no "already shown" exclusion. The override is set by the harness
  in the run context; the agent cannot see or change it. The override drops
  the `property_pending` filter (that flag reflects today, not the window) but
  keeps the recalculable rule and address dedupe.
- Hits are counted by **normalized address**, not ID, so a sent deal deduped
  into its twin (Galena 818/1060, Fort Lauderdale 946/1324) still counts.
- Metrics per case: hits in the shortlist, and hits in the top 20 of the
  agent's last `search_deals` results; compared to the random baseline for the
  pool size. Also store the agent's profile and full trace.
- Runs spend real API money; the script prints the estimated cost and asks for
  confirmation unless `--yes`.
- Also unit tests for scoring, dedupe, address normalization, and
  `present_shortlist` validation, using fixture rows (no DB, no API).

Success bar for the demo (my call): on both cases, the shortlist beats the
random baseline and every "why" is factually consistent with the card numbers.

## 11. Open questions (not blocking v1)

- For Amit, did the team deliberately put cash flow and Florida ahead of tax,
  or was that just availability? Decides how the agent resolves stated-vs-
  reaction conflicts. v1 surfaces conflicts and covers both (§5.2).
- How the acquisition team actually picks deals (the next research step).

## 12. Decisions summary

Decided with the user:
- Chat-thread UI with "why this deal" on each card.
- Agentic tool-use loop, not text-to-SQL; our code builds queries and computes numbers.
- Backend as a new domain in adus-be; one documented read-only exception into iron_bank.
- New schema `deal_recommendation`; separate Next.js frontend project.
- Claude API via the Anthropic SDK Tool Runner; model `claude-sonnet-5-5` at effort `high`; no paid third-party services.
- The UI streams the agent's text and tool steps live.
- No frontend login; no feedback table.
- Goal: leadership demo + full understanding of the internals.

My calls (check these):
- Frontend folder name, stack (Tailwind, shadcn/ui, AI SDK or custom SSE hook).
- Facade module `deal_catalog_service.py` as the single seam.
- Server-side refusal fallback on, 12-tool-call budget.
- Five tools as listed; `get_market_info` dropped for v1.
- Missing metrics score at the 25th percentile.
- Unrecalculable rows (224) excluded from the pool.
- Already-shown: agent resolves labels to IDs; backend enforces exclusion.
- Co-host fee display-only; stored interest rate unless the client gives one.
- Eval: no `property_pending` filter, dedupe on, hits by address.
- Dedupe keeps the latest-approved row per address.
- Local-only demo, no passcode.
- Conflict handling: surface and cover both sides.
- Demo success bar in §10.

Left to the builder: exact function signatures, SSE event names, address
normalization details, system prompt wording, file layout inside the domain,
UI styling.
