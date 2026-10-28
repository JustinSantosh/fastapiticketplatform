# Phase 3: API (Auth, Schemas, Services, Routers)

**Goal:** expose the Phase 2 rules over HTTP, with authentication, validated input, and consistent errors.

## 1. Files

| File | Role |
|---|---|
| `app/auth.py` | bcrypt + `create_access_token` / `decode_access_token` (PyJWT, HS256) + `get_current_user`: `Authorization: Bearer <jwt>` → `User`, or 401 |
| `app/schemas.py` | Pydantic request/response models (the API contract) |
| `app/services.py` | Use-cases: load → check rules → write → commit |
| `app/routers/auth.py`, `tickets.py`, `users.py` | Thin HTTP layer |
| `app/main.py` | Router registration + the 3 exception handlers |

Layering: **router** (HTTP) → **service** (DB + orchestration) → **rules** (pure logic). Routers contain no `if user.is_agent`; all decisions are in `rules.py`.

## 2. Endpoints

| Method | Path | Who | Success | Notable errors |
|---|---|---|---|---|
| POST | `/api/auth/login` | anyone | 200 `{access_token, user}` | 401 bad credentials, 422 |
| GET | `/api/auth/me` | logged in | 200 user | 401 |
| GET | `/api/tickets` | logged in | 200 page | 422 bad filter |
| POST | `/api/tickets` | **user** | 201 ticket | 403 agent, 422 |
| GET | `/api/tickets/{id}` | creator / agent | 200 detail (+comments, history) | **404** other user's ticket |
| POST | `/api/tickets/{id}/status` | **agent** | 200 detail | 400 transition, 403, 404, **409** |
| POST | `/api/tickets/{id}/assign` | **agent** | 200 detail | 400 non-agent assignee, 403, 404, **409** |
| GET | `/api/tickets/{id}/comments` | creator / agent | 200 list | 404 |
| POST | `/api/tickets/{id}/comments` | creator / agent | 201 comment | 404, 422 |
| GET | `/api/users/agents` | **agent** | 200 list | 403 |
| GET | `/api/health` | anyone | 200 | — |

### List query parameters

`GET /api/tickets?status=open&priority=high&assignee=me&q=printer&page=1&page_size=10`

- `status`: `open` | `in_progress` | `resolved`
- `priority`: `low` | `medium` | `high`
- `assignee`: `me` | `unassigned` | `<agent id>`. Validated by regex; anything else returns 422.
- `q`: case-insensitive substring of the title or description. `%` and `_` are escaped, so `50%` is matched literally.
- `page` ≥ 1, `page_size` 1–100 (default 10)
- Sorted newest first, with `id` as a tie-breaker so pages are stable.
- Response: `{items, total, page, page_size, pages}`
- **Users are always restricted to `creator_id = me` inside the SQL query**, so no combination of filters can widen what they see.

### Status change / assign bodies

```json
{ "status": "in_progress", "reason": "Customer says it is still broken", "version": 4 }
{ "assignee_id": 3, "version": 4 }      // null to unassign
```

`version` is required. It is the ticket version the client last saw.

## 3. Authentication flow

1. `POST /api/auth/login` looks up the user by email (lower-cased) and checks the password with bcrypt.
   - It returns the **same message** whether the email or the password was wrong, so the endpoint can't be used to find out which emails have accounts.
2. On success it issues a JWT signed with `JWT_SECRET`: `{"sub": "<user id>", "iat", "exp": now + 120 min}`.
3. Each protected endpoint depends on `get_current_user`, which:
   - returns 401 if the header is missing, the signature is invalid, the token has expired, or the user has been deleted
   - uses `algorithms=["HS256"]` as a whitelist, which blocks `alg: none` attacks
   - **re-reads the user from the DB**, so role checks use the current role, not one stored in the token.

## 4. Validation (Pydantic)

| Field | Rule |
|---|---|
| `title` | stripped, 3–200 chars |
| `description` | stripped, 1–5000 chars |
| `priority` | enum, default `medium` |
| comment `body` | stripped, 1–2000 chars |
| `reason` | stripped, ≤ 1000 chars, optional. *Required for reopen* is a business rule, so it lives in `rules.py`, not the schema. |
| `version` | int ≥ 1 |
| `email` | valid email format (`EmailStr`) |

Strings are stripped before their length is checked, so `"   "` is rejected as empty. The database has `CHECK` constraints as a second line of defence.

**Response models are a whitelist:** `UserOut` has no `hashed_password` field, so the hash can never leak in a response.

## 5. Consistent errors

Every error has the same shape:

```json
{ "detail": "Only the assigned agent can resolve this ticket", "code": "permission_denied" }
```

Validation errors add a per-field list the UI can show next to each input:

```json
{ "detail": "Validation failed", "code": "validation_error",
  "errors": [{ "field": "title", "message": "String should have at least 3 characters" }] }
```

`main.py` owns the single mapping from domain errors to HTTP statuses:

| Exception (rules.py) | HTTP | code |
|---|---|---|
| `NotFound` | 404 | `not_found` |
| `PermissionDenied` | 403 | `permission_denied` |
| `RuleViolation` | 400 | `rule_violation` |
| `VersionConflict` | 409 | `version_conflict` |

## 6. Concurrency in practice

```
Agent A and Agent B both open ticket #7 at version 4.
A: POST /status {in_progress, version 4} → 200, ticket is now version 5
B: POST /assign {..., version 4}         → 409 "your version 4, current version 5"
```

- **Layer 1:** `rules.ensure_version_matches` catches stale clients.
- **Layer 2:** `version_id_col` turns the UPDATE into `... WHERE id = 7 AND version = 4`.
  - If two requests both pass layer 1 at the same instant, Postgres row-locks the row for the first UPDATE.
  - When the lock is released, the second UPDATE re-checks `version = 4`, finds `5`, and matches 0 rows.
  - SQLAlchemy raises `StaleDataError`, which `_commit_ticket_change` converts into the same 409.

**Comments don't use versioning.** They are new rows (append-only), so two people commenting at once can't overwrite each other.

**A no-op update** (assigning a ticket to the agent it already has) sends no UPDATE and doesn't bump the version. Nothing changes, so there is nothing to conflict with.

## 7. Verified (end-to-end, 32/32)

This ran against a throwaway `test` schema, which was dropped afterwards, so real data was untouched:

- **Auth:** wrong password 401 · bad email 422 · no token 401 · forged token 401 · `/me` has no password hash
- **Create:** validation 422 with per-field errors · user creates 201 · agent creates 403
- **Privacy:** Bob reading or commenting on Alice's ticket → 404 · Alice's list only has her own tickets
- **List:** pagination (12 tickets, page 2 of 3 holds 5) · priority filter · `q="50%"` matched literally · bad `assignee` 422 · `page_size=1000` 422
- **Rules:**
  - user can't assign (403) · assigning to a non-agent 400
  - open → resolved 400 · user can't change status (403)
  - non-assignee resolve 403 · assignee resolves 200
  - reopen without a reason 400 · reopen with a reason 200 · history records all 3 moves including the reason
- **Concurrency:**
  - a stale version gets 409 with an explanatory message
  - **two threads fire at the same instant with the same version → exactly one 200 and one 409**, on each of 5 runs
- Also tested against the real DB: `alice@example.com` logs in and sees only her 2 seeded tickets.

## 8. Try it yourself (review gate)

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

1. Open http://127.0.0.1:8000/docs
2. `POST /api/auth/login` with `{"email": "agent.sam@example.com", "password": "Password123!"}` and copy `access_token`
3. Click **Authorize** (top right) and paste the token
4. Try `GET /api/tickets`, then `POST /api/tickets/2/status` with `{"status": "resolved", "version": <current>}`
5. Log in as `agent.priya@example.com` and try to resolve a ticket assigned to Sam → 403
