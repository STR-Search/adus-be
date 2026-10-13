# Underwriting discussions

This is a proposed design, not an applied migration. All five discussion tables live in the **`iron_bank` PostgreSQL schema**. The existing user and media tables remain in their respective schemas.

The initial product has one discussion thread per underwriting. Separating threads from comments allows multiple threads later without moving existing comments.

## Ownership and scope

- Keep discussion models, schemas, repositories, services, and routes within `app/iron_bank/`, following the existing domain structure.
- Use the existing shared authentication dependency to resolve the caller. Do not accept a client-supplied author identity or introduce direct imports between domains.
- Use `app.core.database.Base` for models and the `iron_bank` Alembic branch for migrations.
- Do not modify the `public` schema.
- The proposed ownership is **one thread per underwriting row/version**. A duplicated underwriting starts with no discussion. Sharing a conversation across an entire underwriting series remains a product decision; it would require a different ownership model before implementation.

## Table overview

| Table | Purpose | When needed |
|---|---|---|
| `iron_bank.underwriting_threads` | Owns the discussion for an underwriting | Initial release |
| `iron_bank.underwriting_comments` | Stores comments and optional reply relationships | Initial release |
| `iron_bank.comment_mentions` | Stores distinct users mentioned in each comment | When mentions ship |
| `iron_bank.comment_attachments` | Links comments to existing media records | When attachments ship |
| `iron_bank.thread_subscriptions` | Stores thread notification preferences | When following or notifications ship |

Use database-generated `BIGINT` identity primary keys for threads and comments. Foreign keys to existing underwriting and user records remain `INTEGER`, matching the current models. All timestamps use `TIMESTAMPTZ`.

## 1. `iron_bank.underwriting_threads`

| Column | Type | Null? | Definition |
|---|---|---|---|
| `id` | `BIGINT` | No | Identity primary key |
| `underwriting_id` | `INTEGER` | No | FK to `iron_bank.underwritings.id` |
| `created_by_user_id` | `INTEGER` | No | FK to `users.users.id`; authenticated creator |
| `created_at` | `TIMESTAMPTZ` | No | Server default `now()` |

Constraints and behavior:

- `UNIQUE (underwriting_id)` enforces at most one thread per underwriting.
- Create the thread lazily with the first comment, in the same transaction. Handle concurrent creation using the unique constraint and an upsert/re-fetch strategy.
- When multiple threads become a product requirement, remove that unique constraint and optionally add fields such as `title` or `resolved_at`.
- Reading an underwriting with no thread returns an empty discussion; reads do not create records.

## 2. `iron_bank.underwriting_comments`

| Column | Type | Null? | Definition |
|---|---|---|---|
| `id` | `BIGINT` | No | Identity primary key |
| `thread_id` | `BIGINT` | No | FK to `iron_bank.underwriting_threads.id` |
| `author_user_id` | `INTEGER` | No | FK to `users.users.id`; obtained from authentication |
| `body` | `JSONB` | No | Validated, versioned document described below |
| `parent_comment_id` | `BIGINT` | Yes | Explicit reply target; null for a top-level comment |
| `created_at` | `TIMESTAMPTZ` | No | Server default `now()`; immutable |
| `edited_at` | `TIMESTAMPTZ` | Yes | Set when the body or attachments are edited |
| `deleted_at` | `TIMESTAMPTZ` | Yes | Soft-deletion timestamp |

Constraints and indexes:

- Index `(thread_id, created_at, id)` for chronological retrieval and cursor pagination.
- Add `UNIQUE (thread_id, id)` as the target of a composite self-reference.
- Add a composite FK `(thread_id, parent_comment_id)` referencing `(thread_id, id)` on this table. This prevents replies from pointing into another thread.
- Add `CHECK (parent_comment_id IS NULL OR parent_comment_id <> id)`.
- Keep the parent relationship immutable. Replies may reference only an existing comment; those service rules prevent cycles.
- Before replies ship, require `parent_comment_id` to be null in the API.

Order comments by `(created_at ASC, id ASC)`. A reply relationship does not determine chronological order. This gives deterministic display order, not a strict transaction-commit sequence.

Use bounded cursor pagination. A deleted comment can remain as a placeholder to preserve replies, with its body and attachments omitted from normal responses. Soft deletion does not erase stored content; retention or erasure rules must be decided separately.

## 3. `iron_bank.comment_mentions`

| Column | Type | Null? | Definition |
|---|---|---|---|
| `comment_id` | `BIGINT` | No | FK to `iron_bank.underwriting_comments.id` |
| `user_id` | `INTEGER` | No | FK to `users.users.id` |

- Composite primary key `(comment_id, user_id)`.
- Add index `(user_id, comment_id)` for finding comments that mention a user.
- Store one row per distinct mentioned user, even if that user appears multiple times in the body.
- The backend derives these rows from the validated body. Clients do not submit an independent mention list.
- Save the body and mention rows in one transaction. On edit, replace the relationships to match the new body.

## 4. `iron_bank.comment_attachments`

| Column | Type | Null? | Definition |
|---|---|---|---|
| `comment_id` | `BIGINT` | No | FK to `iron_bank.underwriting_comments.id` |
| `media_id` | Matches existing media ID | No | Reference to the existing media record |
| `position` | `INTEGER` | No | Zero-based display order |

- Composite primary key `(comment_id, media_id)`.
- `UNIQUE (comment_id, position)` and `CHECK (position >= 0)`.
- Add index `(media_id)` for reverse attachment lookups.
- The exact media table name and ID type must be resolved before writing a migration.
- If media lives in another schema in the same database, use a schema-qualified FK, such as `media.files.id`. This name is illustrative, not an assumption about an existing table.
- If media lives in another database or service, use its identifier without a database FK and validate through that service.
- Validate the caller's permission to attach each item and verify the upload is ready.
- Attachment downloads must respect access to the underwriting. Store stable object references in the media catalog, not expiring signed URLs.
- Removing a comment attachment removes the relationship, not the shared media object. Media cleanup belongs to the media lifecycle.

The API may accept an `attachment_ids` array while the database stores individual relationship rows. Array position determines attachment position.

## 5. `iron_bank.thread_subscriptions`

| Column | Type | Null? | Definition |
|---|---|---|---|
| `thread_id` | `BIGINT` | No | FK to `iron_bank.underwriting_threads.id` |
| `user_id` | `INTEGER` | No | FK to `users.users.id` |
| `notification_preference` | `TEXT` | No | Explicit preference: `all`, `mentions_only`, or `none` |
| `created_at` | `TIMESTAMPTZ` | No | Server default `now()` |

- Composite primary key `(thread_id, user_id)`.
- Add index `(user_id, thread_id)` for listing a user's subscriptions.
- A check constraint restricts `notification_preference` to the three supported values.
- A subscription controls notification preferences; it does not grant access.
- Decide automatic subscription and missing-row defaults when notification behavior is designed. Do not infer a permanent subscription solely from having authored a comment.

## Foreign-key deletion policy

Proposed defaults preserve discussion history:

- Use `RESTRICT` for physical deletion of referenced underwritings, threads, users, and parent comments. Routine comment deletion uses `deleted_at`.
- Use `ON DELETE CASCADE` from comments to `comment_mentions` and `comment_attachments`, and from threads to `thread_subscriptions`, for deliberate physical purges.
- For same-database media references, use `RESTRICT` so deleting a media record cannot silently break a live attachment.
- If physical purging is required, implement it explicitly in dependency order and account for reply relationships. Do not let an ordinary underwriting deletion silently erase discussions.

## Comment body format

Store a small, versioned JSON document in `underwriting_comments.body`. The initial format supports paragraphs, plain text, and mentions.

```json
{
  "version": 1,
  "blocks": [
    {
      "type": "paragraph",
      "children": [
        {"type": "text", "text": "Can you check the revenue assumptions, "},
        {"type": "mention", "user_id": 42},
        {"type": "text", "text": "? Please review this with "},
        {"type": "mention", "user_id": 73},
        {"type": "text", "text": "."}
      ]
    }
  ]
}
```

Example rendered text:

> Can you check the revenue assumptions, **@Farhan**? Please review this with **@Alice**.

### Validation and rendering

- Define explicit Pydantic schemas for the versioned document and discriminated node types. Reject unsupported versions, node types, and fields.
- A paragraph contains text or mention nodes. Text nodes contain strings; mention nodes contain stable user IDs.
- Set limits on total text length, block and node counts, and distinct mentions before implementation.
- Require meaningful text, a mention, or at least one valid attachment. Do not accept an empty message accidentally.
- Treat text nodes as plain text, not executable HTML. The frontend renders supported nodes through controlled components.
- The frontend inserts a mention node only after the user selects an eligible account from autocomplete. Typing a name as ordinary text does not create a mention.
- The backend verifies that mentioned users exist, are active, and are eligible to access the underwriting. Mentions never grant access.
- Mention nodes preserve positions without character offsets. Repeated mentions remain separate body nodes but produce one relationship row per user.
- Resolve current display names from user IDs. The API can return a batched user lookup alongside comments. Use a placeholder for unavailable users. If historical labels are required later, add a server-generated display snapshot; identity still comes from the user ID.

For comment `501`, the example body produces these mention relationships:

| comment_id | user_id |
|---|---|
| 501 | 42 |
| 501 | 73 |

The body is the source of truth for authored content. The mention table is a transactionally maintained relationship projection for queries and future notifications.

### Example create-comment request

```json
{
  "body": {
    "version": 1,
    "blocks": [
      {
        "type": "paragraph",
        "children": [
          {"type": "text", "text": "Here is the revised estimate, "},
          {"type": "mention", "user_id": 42},
          {"type": "text", "text": "."}
        ]
      }
    ]
  },
  "parent_comment_id": null,
  "attachment_ids": [801, 802]
}
```

Attachment IDs above assume integer media IDs for illustration. Use the actual media ID type in the request schema. Attachments render beneath the body; inline media nodes are not part of this initial format.

The route identifies the underwriting/thread. The backend obtains the author from authentication, checks access, validates the body and attachments, and saves the comment and all relationships in one transaction.

## Counts and notifications

Initially calculate the count of non-deleted comments. For underwriting lists, fetch counts for the page in a grouped query rather than issuing one query per underwriting.

If measured query cost justifies caching, add `comment_count` to the thread. Maintain it using atomic database updates in the same transaction as creates and deletes, and provide reconciliation against actual rows. Do not initially duplicate the count on underwritings.

When notifications ship, add a transactional outbox as separate delivery infrastructure: write the comment change and its event in the same database transaction, then process the event in a worker. Retry safely and deduplicate deliveries. Exclude the actor, respect preferences, and recheck recipient access. On edits, distinguish newly added mentions from existing ones to avoid repeated alerts.

An outbox is not required for the initial comment-only release, and no notification delivery system is specified by these five tables.

## References

- [PostgreSQL array guidance](https://www.postgresql.org/docs/15/arrays.html): relationship tables are preferable to array columns when the values represent a relational set.
- [Transactional outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html): persist outgoing events atomically with application changes.
