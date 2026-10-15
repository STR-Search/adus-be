# Underwriting Discussions — Design

Status: **Proposal** · Scope: comment threads on underwritings, designed to extend
to other entities, @mentions, media attachments, and future notifications.

---

## 1. Goals & constraints

- One comment thread per underwriting **today**, keyed on the underwriting's own
  `id` (each version of an underwriting has its own thread). Multiple threads
  (per section, internal vs client, etc.) must be possible later without
  reshaping data.
- Other entities (markets, listings, …) may get threads later.
- No notification system yet, but the data model must make one easy to bolt on.
- @mentions must be reliable server-side (notifications, "mentions of me",
  rename-safe rendering).
- Attachments will come from a shared `media` table living in another schema.

## 2. Key design decisions

### 2.1 `threads` is a first-class table

Comments never point directly at an underwriting — they point at a thread, and
the thread points at the subject.

- **Multiple threads later = no migration of comments.** Today a partial unique
  index enforces one `general` thread per underwriting; later, add new `kind`
  values or drop the index.
- **Natural subscription unit** for notifications ("who's in this conversation").
- **Home for denormalized counters** (`comment_count`, `last_comment_at`) if ever
  needed — never on `underwritings` (see 2.4).
- Threads are created lazily on the first comment.

### 2.2 Ordering: `(created_at, id)`, not a linked list

A `reference_id` → previous-comment linked list was considered and rejected:

- **Races:** two concurrent posts both read "last = 17" and both write
  `reference_id = 17` → forked chain, and the DB can't prevent it.
- **Reads need a recursive CTE** instead of `ORDER BY`.
- **Pagination breaks** ("20 before X" becomes a chain walk).
- **Deletes break the chain** unless neighbours are relinked.

Comments are append-only and chronological, so order is intrinsic. Index
`(thread_id, created_at, id)` and use keyset pagination:
`WHERE thread_id = :t AND (created_at, id) < (:c, :i) ORDER BY created_at DESC, id DESC LIMIT 20`.

Branching replies are a different concept ("reply-to", not "comes-after") and
will be a nullable `parent_comment_id` — a trivial additive migration later.

IDs: `bigint` identity, consistent with the rest of the codebase.

### 2.3 @mentions: FE owns the UX, BE owns the data

The frontend provides the typeahead / picker. The backend must own mention data,
otherwise it can't notify, query "mentions of me", or survive user renames.

- Body is stored as **structured JSON nodes** (section 4), not text with tokens.
- Server extracts mentioned user ids from the body, validates them, and writes
  `comment_mentions`. The client never sends a separate mention list (it could
  disagree with the body).
- FE renders mention nodes using **current** user names returned by the API.

### 2.4 Denormalized comment count

Start by computing it (indexed `count(*)` per thread is cheap, including grouped
counts for the list page). Measure with `ProfilingMiddleware`.

If it ever needs denormalizing, put `comment_count` / `last_comment_at` on
**`threads`**, updated in the same transaction as the insert. **Not** on
`underwritings`: it's a wide, hot row analysts edit constantly — bumping it on
every comment adds lock contention and pollutes `updated_at`.

### 2.5 Media: join table, not an array column

A `media_ids int[]` column has no FK integrity, no cascade, poor reverse lookup,
and nowhere for per-attachment metadata. Use `comment_attachments(comment_id,
media_id, position)`.

Expected upload flow: client requests a presigned URL → `media` row created as
`pending` → client uploads directly to storage → comment create references the
media ids → server attaches them and marks `active` → sweeper cleans orphaned
`pending` rows.

### 2.6 Notifications: what we build now vs later

**Now (cheap):**
- `thread_participants` (author / mentioned / manual, read state, muted) — gives
  unread counts immediately and *is* the future recipient list.
- A single write path (`CommentService.create()` / `.update()`) so there is
  exactly one place to hook notifications in.

**Later:**
- Transactional outbox (`comment.created` event row written in the same
  transaction; a worker fans out notifications).
- `notifications` table — per-recipient state, separate from comments.

### 2.7 Edits & deletes

- Soft delete via `deleted_at`; render "comment deleted" so replies stay coherent.
- `edited_at` set on edit. On edit, diff old vs new mention sets so only newly
  added mentions notify (later).
- Open: author-only edit/delete, or admins too?

---

## 3. Tables

| Table | Purpose | When |
|---|---|---|
| `discussions.threads` | A conversation attached to a subject (underwriting) | v1 |
| `discussions.comments` | The messages | v1 |
| `discussions.comment_mentions` | Who each comment @mentions (server-derived from body) | v1 |
| `discussions.thread_participants` | Who's in a thread + read state (future notification recipients) | v1 |
| `discussions.comment_attachments` | Join table from comments to the shared `media` table | when media exists |

External tables referenced: `iron_bank.underwritings`, `users.users`,
`media.media` (placeholder name — replace with the real media table).

```
iron_bank.underwritings ─1───*─ threads ─1───*─ comments ─*───1─ users.users (author)
                                   │               │  └─ parent_comment_id (self, later)
                                   │               ├─1───*─ comment_mentions ─*───1─ users.users
                                   │               └─1───*─ comment_attachments ─*───1─ media.media
                                   └─1───*─ thread_participants ─*───1─ users.users
```

---

## 4. Comment body structure

Stored as `jsonb` — a versioned list of typed nodes:

```json
{
  "version": 1,
  "nodes": [
    { "type": "text",    "text": "Hey " },
    { "type": "mention", "user_id": 42 },
    { "type": "text",    "text": ", ADR looks high vs the comp set.\nCan you re-check?" },
    { "type": "link",    "href": "https://...", "text": "AirDNA export" }
  ]
}
```

**Why nodes over inline tokens (`Hey @[user:42]`) in a text column:**

- **No escaping/parsing ambiguity** — a user can't forge a mention by typing
  token syntax.
- **Validation is Pydantic** — a discriminated union on `type`; malformed → 422.
- **Mention extraction is trivial** — `[n.user_id for n in nodes if n.type == "mention"]`.
- **Extensible** — new node types (`underwriting_ref`, `media_embed`, `emoji`)
  don't break old comments; `version` allows migrating to a full rich-text format
  (TipTap/ProseMirror) if the FE adopts one.

**Server pipeline on create/edit:**

1. Validate `nodes` against the Pydantic union.
2. Collect mentioned `user_id`s; verify they exist and aren't deleted.
3. Write `comment_mentions`; upsert `thread_participants` with `reason='mentioned'`.
4. Compute `body_text` (e.g. `Hey @Jane Doe, ADR looks high…`) for search,
   previews, and future notification snippets.

**API response** includes referenced users so the FE renders current names
without extra requests:

```json
{
  "id": 981,
  "author": { "id": 7, "first_name": "Sam", "last_name": "Lee" },
  "body": { "version": 1, "nodes": [ "..." ] },
  "users": { "42": { "id": 42, "first_name": "Jane", "last_name": "Doe" } },
  "attachments": [ { "media_id": 55, "url": "...", "mime_type": "image/png" } ],
  "created_at": "...",
  "edited_at": null,
  "is_deleted": false
}
```

---

## 5. Referencing the subject from a generic `discussions` schema

The `discussions` schema is meant to serve more than underwritings, so `threads`
needs to reference "the thing being discussed" without losing integrity. Two
options:

### Option A — Polymorphic `subject_type` + `subject_id`

```sql
threads (id, subject_type text, subject_id text, ...)
-- ('underwriting', '123'), ('market', '45'), ('listing', '2087341')
```

Fully generic, but:

- **No FK.** Postgres can't point one column at many tables; nothing stops
  `subject_id = '99999'` referencing a nonexistent underwriting.
- **No cascade.** Deleting an underwriting orphans its threads unless app code
  remembers to clean up.
- **Mixed id types.** `underwritings.id` is int, `series_id` is uuid, `zpid` is
  text → `subject_id` must be `text`; ugly joins, zero type safety.

This is what Rails/Django do, relying on the app for integrity.

### Option B — Exclusive arc: one nullable FK column per subject type (recommended)

```sql
CREATE TABLE discussions.threads (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind             text NOT NULL DEFAULT 'general',

    -- one nullable FK per discussable entity
    underwriting_id  integer REFERENCES iron_bank.underwritings(id) ON DELETE CASCADE,
    -- later:
    -- market_id     integer REFERENCES markets.markets(id) ON DELETE CASCADE,
    -- zpid          text    REFERENCES zillow.scheduled_listings(zpid) ON DELETE CASCADE,

    created_at       timestamptz NOT NULL DEFAULT now(),

    -- a thread belongs to exactly one subject
    CONSTRAINT ck_threads_one_subject
        CHECK (num_nonnulls(underwriting_id) = 1)
        -- later: num_nonnulls(underwriting_id, market_id, zpid) = 1
);
```

- Only `threads` is subject-aware; comments / mentions / participants /
  attachments hang off `thread_id` and stay fully generic.
- Every subject column is a real FK with the correct type and cascade.
- Adding a new discussable entity = one migration (nullable column + partial
  unique index + widened CHECK). That's appropriate: "what can be discussed" is a
  product decision.

**Fit with "never import between domains":** the rule is about Python imports.

- Models use `ForeignKey("iron_bank.underwritings.id")` — a string resolved
  through the shared `Base.metadata`; `discussions` never imports `Underwriting`.
- The generic service takes a subject descriptor:
  ```python
  class ThreadSubject(Enum):
      UNDERWRITING = "underwriting_id"
      # MARKET = "market_id"

  await thread_service.get_or_create(subject=ThreadSubject.UNDERWRITING, subject_id=123)
  ```
  Existence is enforced by the FK; an FK violation maps to 404.
- Routes stay entity-shaped for the FE (`/underwritings/{id}/comments`), served
  by the `discussions` router.

**Not covered by B:** per-entity authorization ("can user X comment on
underwriting 123?"). Today every authenticated user can see everything. If that
changes, add a small per-`ThreadSubject` permission-checker registry in
`app/core/`.

> A third option — per-domain link tables (`iron_bank.underwriting_threads`) —
> was considered and rejected: it pushes subject ownership back into each domain,
> which defeats the purpose of a standalone `discussions` schema.

---

## 6. Full schema (PostgreSQL, using Option B)

```sql
CREATE SCHEMA discussions;

-- ── threads ────────────────────────────────────────────────────────────────
CREATE TABLE discussions.threads (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind             text NOT NULL DEFAULT 'general',
    underwriting_id  integer
                     REFERENCES iron_bank.underwritings(id) ON DELETE CASCADE,
    created_at       timestamptz NOT NULL DEFAULT now(),
    -- later, only if profiling says so:
    -- comment_count   integer NOT NULL DEFAULT 0,
    -- last_comment_at timestamptz,
    CONSTRAINT ck_threads_one_subject CHECK (num_nonnulls(underwriting_id) = 1)
);

-- One 'general' thread per underwriting today; drop/relax to allow more.
CREATE UNIQUE INDEX uq_threads_underwriting_general
    ON discussions.threads (underwriting_id)
    WHERE kind = 'general' AND underwriting_id IS NOT NULL;

-- ── comments ───────────────────────────────────────────────────────────────
CREATE TABLE discussions.comments (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id          bigint NOT NULL
                       REFERENCES discussions.threads(id) ON DELETE CASCADE,
    author_user_id     integer NOT NULL
                       REFERENCES users.users(id) ON DELETE RESTRICT,
    body               jsonb NOT NULL,
    body_text          text  NOT NULL,          -- server-derived plain text
    created_at         timestamptz NOT NULL DEFAULT now(),
    edited_at          timestamptz,
    deleted_at         timestamptz,             -- soft delete
    -- later (branching replies), nullable so it's additive:
    -- parent_comment_id bigint REFERENCES discussions.comments(id) ON DELETE CASCADE,
    CONSTRAINT ck_comments_body_object CHECK (jsonb_typeof(body) = 'object')
);

-- Thread timeline + keyset pagination
CREATE INDEX idx_comments_thread_timeline
    ON discussions.comments (thread_id, created_at, id);

CREATE INDEX idx_comments_author ON discussions.comments (author_user_id);

-- ── comment_mentions ───────────────────────────────────────────────────────
CREATE TABLE discussions.comment_mentions (
    comment_id  bigint  NOT NULL
                REFERENCES discussions.comments(id) ON DELETE CASCADE,
    user_id     integer NOT NULL
                REFERENCES users.users(id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (comment_id, user_id)
);

-- "Comments that mention me" / notification fan-out
CREATE INDEX idx_comment_mentions_user
    ON discussions.comment_mentions (user_id, created_at DESC);

-- ── thread_participants ────────────────────────────────────────────────────
CREATE TABLE discussions.thread_participants (
    thread_id             bigint  NOT NULL
                          REFERENCES discussions.threads(id) ON DELETE CASCADE,
    user_id               integer NOT NULL
                          REFERENCES users.users(id) ON DELETE CASCADE,
    reason                text    NOT NULL,     -- 'author' | 'mentioned' | 'manual'
    last_read_comment_id  bigint
                          REFERENCES discussions.comments(id) ON DELETE SET NULL,
    muted                 boolean NOT NULL DEFAULT false,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, user_id),
    CONSTRAINT ck_thread_participants_reason
        CHECK (reason IN ('author', 'mentioned', 'manual'))
);

CREATE INDEX idx_thread_participants_user
    ON discussions.thread_participants (user_id);

-- ── comment_attachments (once media exists) ────────────────────────────────
CREATE TABLE discussions.comment_attachments (
    comment_id  bigint   NOT NULL
                REFERENCES discussions.comments(id) ON DELETE CASCADE,
    media_id    bigint   NOT NULL
                REFERENCES media.media(id) ON DELETE RESTRICT,
    position    smallint NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (comment_id, media_id)
);

CREATE INDEX idx_comment_attachments_media
    ON discussions.comment_attachments (media_id);
```

**Notes**

- `ON DELETE RESTRICT` on comment author — users are soft-deleted
  (`is_deleted`); a hard delete shouldn't silently wipe their comments.
- If `media` lives in another schema of the same Postgres DB, the cross-schema FK
  works. If it's a separate service/DB, drop the FK and validate `media_id` in
  `CommentService`.
- Unread count = comments in the thread with `id > last_read_comment_id` for the
  user's participant row.
- `reason` uses a CHECK; could use `reference.enum_options` slugs instead, but a
  CHECK is simpler for a tiny internal set.

---

## 7. API sketch

```
GET    /underwritings/{id}/comments?cursor=&limit=
POST   /underwritings/{id}/comments
PATCH  /comments/{id}
DELETE /comments/{id}
```

The thread stays an internal detail until more than one per underwriting exists.

---

## 8. Open questions

1. **Domain placement.** New `app/discussions/` domain + `discussions` schema
   (recommended) means a fifth Alembic branch.
2. **Edit/delete permissions.** Author-only, or admins too?
3. **Media table.** Final name/location of the shared media table, and whether
   it's in the same database.
