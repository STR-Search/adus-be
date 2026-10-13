# Underwriting comments — frontend handoff

Branch: `feat/comments`. Backend design: `docs/underwriting_discussions.md` (§7 is the composer contract). This note is the subset the frontend has to implement.

v1 is one comment thread per underwriting **row**. Replies, unread badges, notifications, and attachments are not in this release. A duplicated underwriting starts with an empty thread; comments stay on the original row.

Auth is the existing global guard (`Authorization: Bearer <jwt>` or `X-ADUS-API-KEY`). The author is always the authenticated user. Do not send `author_user_id`; unknown fields are rejected with `422`.

---

## Endpoints

| Method | Path | Success |
|---|---|---|
| `GET` | `/iron-bank/underwritings/{id}/comments?page=&page_size=` | `200` page |
| `POST` | `/iron-bank/underwritings/{id}/comments` | `201` comment |
| `PATCH` | `/comments/{comment_id}` | `200` comment |
| `DELETE` | `/comments/{comment_id}` | `204` empty body |

`page` is 1-based. `page_size` is `25` (default), `50`, or `100`. Anything else is `422`.

Opening the thread does not create it. A underwriting with no comments returns an empty page (`total: 0`, `pages: 0`). The thread is created on the first successful `POST`.

Comments are newest first (`created_at`, then `id`). A comment posted between page loads can shift later pages by one, so page 2 can repeat the last item of page 1. De-duplicate by `id`.

---

## Requests

Create:

```json
{
  "body_version": 1,
  "body": { "type": "doc", "content": [] },
  "parent_comment_id": null
}
```

`parent_comment_id` is optional and must be `null`. A non-null value is `422` (`type: "replies_not_supported"`).

Edit sends only the body:

```json
{
  "body_version": 1,
  "body": { "type": "doc", "content": [] }
}
```

`body` is Tiptap `editor.getJSON()`. `body_version` sits beside it, not inside the JSON. The stored body is the server-normalized document; load it back with `editor.commands.setContent(body)`.

---

## Responses

A comment:

```json
{
  "id": 981,
  "thread_id": 88,
  "author_user_id": 7,
  "parent_comment_id": null,
  "body_version": 1,
  "body": { "type": "doc", "content": [] },
  "created_at": "2026-10-08T14:02:00Z",
  "edited_at": null,
  "is_deleted": false
}
```

`POST` and `PATCH` return that object plus a `users` map. `GET` returns a page:

```json
{
  "items": [],
  "users": {
    "7": {
      "id": 7,
      "first_name": "Sam",
      "last_name": "Lee",
      "email": "sam@example.com",
      "is_deleted": false
    }
  },
  "total": 2,
  "page": 1,
  "page_size": 25,
  "pages": 1
}
```

`users` covers the authors on the page and the users mentioned in non-deleted comments on the page. JSON object keys are strings; `id` inside each user is a number. A soft-deleted user is still present, with `is_deleted: true`. A user id missing from the map has no row to display.

Show edit and delete only when `author_user_id` is the current user and `is_deleted` is false. Editing or deleting someone else's comment is `403`. Editing or deleting a missing or already-deleted comment is `404` (`{"detail": "Comment not found"}`).

A deleted comment stays in the list as a placeholder: `is_deleted: true`, `body: null`. Render “Comment deleted”. `total` counts these placeholders. `edited_at` is set after a successful edit and is otherwise `null`.

---

## Underwriting list

Both list responses — the normal list and simulation mode — add `discussion` on every row:

```json
"discussion": {
  "thread_id": 88,
  "comment_count": 4,
  "last_comment_at": "2026-10-08T14:02:00Z"
}
```

No thread yet:

```json
"discussion": { "thread_id": null, "comment_count": 0, "last_comment_at": null }
```

`comment_count` is non-deleted comments only. A thread whose comments were all deleted keeps its `thread_id` and returns `comment_count: 0`. Use the comments endpoint’s `total` for pagination; it includes deleted placeholders, so it can be higher than `comment_count`.

`GET /iron-bank/underwritings/{id}` (the edit context) does not include `discussion`. Load the thread from the comments endpoint when the detail view opens.

---

## Composer

The editor is `RichTextEditor` in the frontend repo (`components/rich-text-editor.tsx`, Tiptap v3). If that component only reports HTML today, add a callback that returns `editor.getJSON()` for the comment composer. Submit that JSON. Render stored comments with Tiptap’s static renderer, and insert comment content as structured nodes rather than as HTML.

Enable exactly these extensions. Tiptap’s StarterKit turns on headings, blockquotes, code blocks, and horizontal rules; turn those off for this composer.

| Kind | Allowed |
|---|---|
| Blocks | `doc`, `paragraph`, `bulletList`, `orderedList` (`attrs.start`), `listItem` |
| Inline | `text`, `hardBreak`, `mention` |
| Marks | `bold`, `italic`, `strike`, `underline`, `code`, `link` |

Shape:

- `doc` contains one or more of `paragraph`, `bulletList`, `orderedList`.
- `paragraph` contains zero or more inline nodes. An empty paragraph may omit `content`.
- A list contains one or more `listItem`s.
- `listItem` starts with a `paragraph`, then optional nested lists. Max list depth is 3.

`orderedList.attrs.start` defaults to `1` and is always present on the stored body.

### Mentions

Use `@tiptap/extension-mention`. Feed the picker from `GET /users` (unpaginated, active users only, ordered by name). Filter that list on the client. There is no search query param yet.

A mention exists only when the user picks someone. Typed `@Name` is plain text. The node the server keeps is:

```json
{ "type": "mention", "attrs": { "id": 42 } }
```

`id` is a positive integer. `"42"` is accepted and stored as `42`. `label` and `mentionSuggestionChar` are dropped. Resolve the display name from `users[id]` at render time, so a rename shows up without rewriting old comments. If the id is missing from `users`, or `is_deleted` is true, render “Former user”. Highlight the chip when the id is the current user.

Mentioning an unknown or deleted user fails the whole comment with `422`:

```json
{
  "detail": [
    {
      "loc": ["body"],
      "msg": "Mentioned users do not exist or are deleted",
      "type": "invalid_mention",
      "ctx": { "user_ids": [99] }
    }
  ]
}
```

### Links and marks

A link mark keeps `href` only. It must be an absolute `http` or `https` URL, at most 2048 characters. `target`, `rel`, and `class` are dropped. When rendering, use `<a target="_blank" rel="noopener noreferrer">`.

| Node / mark | Render |
|---|---|
| `paragraph`, lists | `<p>`, `<ul>` / `<ol>` / `<li>` |
| `text` + marks | `strong`, `em`, `s`, `u`, `code` |
| `hardBreak` | `<br>` |
| unknown node | inner text if any, otherwise skip |

### Limits

Enforce these in the composer. The server enforces the same values and is authoritative.

| Limit | Value |
|---|---|
| Text characters | 10,000 |
| Nodes (marks excluded) | 1,000 |
| Distinct mentions (`42` and `"42"` count once) | 20 |
| List nesting | 3 |
| Node depth | 8 |

An empty comment is rejected: the body needs non-whitespace text or at least one mention. Tiptap’s empty doc (`doc` → empty `paragraph`) is empty.

---

## Errors

`422` uses FastAPI’s list shape: `{"detail": [{"loc", "msg", "type", "ctx"?}]}`.

| Case | Status | How to recognise it |
|---|---|---|
| Underwriting does not exist | `404` | `{"detail": "Underwriting not found"}` |
| Comment missing, or already deleted (edit/delete) | `404` | `{"detail": "Comment not found"}` |
| Edit/delete by someone other than the author | `403` | `{"detail": "Only the author can modify this comment"}` |
| Bad body shape, unknown node/mark, over a limit, empty | `422` | `loc` starts at `"body"` (or `"body_version"` for an unsupported version) |
| Unknown or deleted mention | `422` | `type: "invalid_mention"`, `ctx.user_ids` |
| `parent_comment_id` set | `422` | `type: "replies_not_supported"` |
| Extra field such as `author_user_id` | `422` | request validation |

Unknown node or mark types mean the composer and the server have drifted. Fix the extension list rather than special-casing the error.

---

## Out of scope for this UI

- Replies. `parent_comment_id` is always `null` on read.
- More than one thread per underwriting. There is a single general thread; the client does not send a thread kind.
- Unread counts, read receipts, and `POST /threads/{id}/read`.
- Notifications.
- Attachments.
- A `discussion` object on the single-underwriting GET.
