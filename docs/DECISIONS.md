# Technical Decisions and Trade-offs

## 1. FastAPI over Django

**Chosen:** FastAPI + SQLAlchemy 2.0 + Pydantic v2.

- The hard parts of this brief are explicit **business rules, validation and permissions**. In FastAPI each of these is plain, visible Python:
  - a Pydantic model is the request contract
  - `Depends(get_current_user)` is the auth check
  - `rules.py` holds the rules
- Swagger docs at `/docs` come for free, which makes the API easy to review and demo.
- **Trade-off:** Django would give an admin site, built-in auth and migrations out of the box. Here I wired up JWT, Alembic and the session handling myself. That is a little more code, but nothing is hidden, so I can explain every line.
- **Synchronous, not async, SQLAlchemy.** It is simpler to reason about and test, and at this scale there is no throughput benefit to async DB I/O.

## 2. Layering: routers → services → pure rules

- Routers only translate HTTP. Services orchestrate load, check, write, commit. `rules.py` holds every business rule as a **pure function** that raises a domain exception.
- One handler in `main.py` maps those exceptions to HTTP codes (`NotFound` → 404, `PermissionDenied` → 403, `RuleViolation` → 400, `VersionConflict` → 409).
- **Why:**
  - Each rule is written exactly once, in one file, and reads like the spec.
  - It can be unit-tested without a DB (`test_rules.py` covers all 9 transition pairs).
  - Changing a rule live (for example, letting creators reopen) is a one-line change plus a test.

## 3. Permissions

| Concern | Approach |
|---|---|
| Where | **Server only.** The UI hides buttons for convenience, but every endpoint re-checks. Tests call the API directly to prove this. |
| Role source | Read from the **DB on every request**. The JWT carries only the user id, so a role change takes effect immediately. |
| Privacy for users | Applied in two places: (1) the list query always adds `WHERE creator_id = me` for users, whatever filters are sent; (2) single-ticket endpoints use `ensure_can_view`. |
| **404 vs 403** for another user's ticket | **404**, with exactly the same body as a nonexistent ticket, so users can't probe which ticket ids exist. (Tested byte for byte.) |
| Check order | view (404) → permission (403) → version (409) → transition (400). A non-assignee gets "not allowed" before learning anything about transitions. A stale client is told to reload before seeing a transition error that may no longer apply. |

## 4. Status transitions

```python
ALLOWED_TRANSITIONS = {
    OPEN:        {IN_PROGRESS},
    IN_PROGRESS: {RESOLVED},
    RESOLVED:    {IN_PROGRESS},   # reopen, reason required
}
```

- It is a **whitelist**, so anything not listed (skipping a step, going backwards, a "same → same" move) is rejected.
- **The reopen reason is stored in a `ticket_status_changes` table**, not a column on `tickets`. That keeps *every* reason across several reopens and gives a full audit trail (who, when, from, to). The extra table is the cost.
- Status changes and assignment are separate endpoints (`/status`, `/assign`) instead of one generic `PATCH`. Each has its own small, explicit rule set and request body.

## 5. Concurrent updates: optimistic locking

**Problem:** two agents open the same ticket. A resolves it and B reassigns it from their stale view. Without protection, B's write silently overwrites A's.

**Solution:** a `version` column with two layers:
1. **Stale client:** every edit sends the `version` the client loaded. If it doesn't match the DB, return **409**.
2. **Race at the DB:** two requests could pass check 1 at the same instant, so SQLAlchemy's `version_id_col` makes the UPDATE conditional: `WHERE id = :id AND version = :seen`. Postgres row-locks during UPDATE, so the second writer re-evaluates the condition, matches 0 rows, and gets `StaleDataError` → **409**. The whole transaction is rolled back, including its history row.

**Why optimistic, not pessimistic (`SELECT … FOR UPDATE`):**
- Conflicts on a support ticket are rare. Optimistic locking holds no locks while people read, and it costs nothing when there is no conflict.
- A row lock only lasts for one DB transaction, so it **can't detect a stale browser tab** that loaded the ticket minutes ago. The version number can.
- **Trade-off:** the losing user has to reload and redo their action. The UI makes this explicit with a banner, not a silent failure.

**Verified by tests:** stale version → 409 and nothing changes; a deterministic two-session race; and a real two-thread HTTP race, repeated 5 times, which always gives exactly one 200 and one 409. With layer 1 disabled, the race tests *still* pass because of layer 2.

**Not versioned:** comments. They are inserts and can't overwrite anything, so two people commenting at once is fine and doesn't bump the ticket version.

## 6. Authentication: JWT bearer tokens

- Login checks the password with **bcrypt** (salted, deliberately slow) and returns an HS256-signed JWT `{sub: user_id, iat, exp: +120 min}`.
- Wrong email and wrong password give the **same** 401 message, to prevent finding out which emails have accounts.
- `algorithms=["HS256"]` is passed as a whitelist when decoding, which blocks `alg: none` forgeries.
- `JWT_SECRET` is 48 random bytes, kept in `.env` (git-ignored), never in the repo.
- **Trade-off: storing the token in `localStorage`.** It is simple, survives a reload, and needs no CSRF handling. The risk is that an XSS bug could read it. React escapes all output and the app never uses `dangerouslySetInnerHTML`; the 120-minute expiry limits the damage. The alternative, an **httpOnly cookie**, can't be read by JavaScript but needs CSRF tokens and a cookie-aware CORS setup. I would switch to it for production.
- **Trade-off: no refresh tokens or revocation.** A token stays valid until it expires. Rotating `JWT_SECRET` invalidates every token at once (an emergency kill switch).

## 7. Validation in three places

| Layer | Purpose |
|---|---|
| React forms | Instant feedback. The limits are copied from the backend (`LIMITS` in `lib/tickets.js`). |
| **Pydantic** (authoritative) | Strips whitespace *then* checks lengths, so `"   "` counts as empty. Returns per-field 422 errors in a shape the UI shows under each input. |
| PostgreSQL CHECKs | A last line of defence for anything that bypasses the API. |

## 8. Database choices

See [DATABASE.md](DATABASE.md). In short:
- Enums are VARCHAR + CHECK, which is easier to migrate than native enums.
- Deliberate `ON DELETE` rules: RESTRICT for authorship, SET NULL for the assignee, CASCADE for comments and history.
- Indexes match the dashboard queries.
- Alembic for migrations. The migration reads the URL from `.env`, so `alembic.ini` contains no credentials.

## 9. Testing approach

- **Real PostgreSQL, not SQLite.** The concurrency guarantees depend on Postgres row locking, and SQLite would test a different database.
- Tests run in a separate `test` schema of the same database. The fixture refuses to run if it would point at app data.
- **TRUNCATE after each test** instead of rolling back a wrapping transaction. The race tests need separate connections that see each other's commits.
- Tests arrange state directly in the DB (`make_ticket(alice, status=RESOLVED, assignee=sam)`) and exercise the action under test through the real HTTP API.
- To show the tests have teeth, each rule was disabled in turn: every one is caught by 4–12 failing tests.

## 10. Frontend choices

- **No UI or component library, no global state library**, to stay on the required stack: React + react-router + plain CSS with design tokens (light and dark).
- Dashboard **filters live in the URL**, so reload, back/forward and shareable links work for free.
- `AbortController` cancels stale list requests, so a slow old response can't overwrite a newer one.
- A 409 shows a dedicated "changed by someone else, reload" banner rather than a generic error or a silent auto-reload.
- One `<table>` that CSS turns into stacked cards on phones, instead of two separate layouts.

## 11. Assumptions

1. Only **users** create tickets; agents work on them.
2. Only **agents** change status or assignment. Creators can't reopen; they comment instead.
3. Any agent can start or reopen a ticket. **Only the assigned agent can resolve it**, so a ticket must be assigned before it can be resolved.
4. Only agents can be assignees. Any agent may reassign or unassign.
5. Agents can comment on any ticket; users only on their own.
6. No self-registration; accounts come from the seed script.
7. Moving a ticket to the status it already has is rejected (400), not treated as a no-op.

## 12. What I'd do next, with more time

- An httpOnly cookie session with CSRF protection, plus refresh tokens.
- Frontend tests (Vitest + React Testing Library) for the forms and the 409 banner.
- Editing ticket fields (with the same version check), and editing or deleting comments.
- Rate limiting on `/auth/login`.
- Live updates (SSE or WebSocket), so a viewer learns a ticket changed *before* trying to save.
- A trigram index for search at scale; Docker Compose for one-command setup; CI running pytest.
