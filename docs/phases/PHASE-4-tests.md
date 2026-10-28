# Phase 4: Automated Tests

**Goal:** prove every rule in the brief with repeatable tests that run locally against real PostgreSQL.

## 1. Run them

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest                     # whole suite (~10 s)
pytest -v                  # one line per test
pytest tests/test_concurrency.py -v
pytest -k "resolve"        # tests whose name matches
```

Prerequisite: `TEST_DATABASE_URL` in `backend/.env` (see `.env.example`). It points at the same `Yalla & co` database with `search_path=test`.

**Result: 79 passed**, consistently across 4 consecutive runs.

## 2. How the test environment works (`tests/conftest.py`)

| Concern | Approach |
|---|---|
| **Which DB** | Real Postgres, not SQLite. Row locking, `CHECK` constraints and `ILIKE` behave the same as in production. |
| **Not touching real data** | Tables are created in a separate **`test` schema**. Before running, the fixture checks that `TEST_DATABASE_URL` differs from `DATABASE_URL` and that the connection's `current_schema()` really is `test`; otherwise pytest aborts. Verified after the run: `public` still has its 4 users and 3 tickets, and the `test` schema is empty. |
| **Clean state per test** | `TRUNCATE … RESTART IDENTITY CASCADE` after every test. |
| **Clean state per run** | `drop_all` + `create_all` at the start (so a crashed earlier run doesn't matter) and `drop_all` at the end. |
| **API calls** | FastAPI `TestClient` with `get_db` overridden, so each request gets its own session on the test DB, just like production. |
| **Auth in tests** | `auth(user)` builds a real signed JWT with `create_access_token`. The login endpoint itself is tested separately. |
| **Arranging state** | The `make_ticket(alice, status=RESOLVED, assignee=sam)` fixture inserts directly into the DB, so each test exercises only the one API action it is about. |
| **Speed** | The bcrypt hash is computed once per run, not once per user per test. |

**Why TRUNCATE instead of a rolled-back transaction per test?** The race tests need two *separate* database connections that see each other's commits. A wrapping transaction would hide one connection's writes from the other, which would make it impossible to test the very thing we care about. This differs from the original plan, which said "rolled-back transaction".

## 3. What is covered

| Brief requirement | File | Tests |
|---|---|---|
| **Authorization & user ticket privacy** | `test_auth_privacy.py` | 19 |
| **Allowed & disallowed status transitions** | `test_rules.py` (all 9 from→to pairs) + `test_status_transitions.py` | 22 + 12 |
| **Assigned-agent resolve permission** | `test_resolve_permission.py` | 6 |
| **Concurrent update / conflict handling** | `test_concurrency.py` | 10 |
| Filtering & pagination | `test_tickets_list.py` | 12 |

### Highlights

**Privacy**
- Bob reading, listing or commenting on Alice's ticket gets 404.
- The response for "someone else's ticket" is **byte-for-byte identical** to "ticket doesn't exist", so nothing leaks.
- A user's list never contains other users' tickets, whatever filters they send (`assignee=<agent>`, `q=…`, `page_size=100`).
- Missing, malformed, forged (wrong secret) and expired tokens all get 401.
- A wrong password and an unknown email produce the same 401 body.

**Transitions**
- The full 3×3 matrix: the 3 allowed moves pass and the other 6 are rejected.
- At the API level, a rejected move leaves status, version and history **unchanged**.
- Reopening with `null`, `""` or `"   "` as the reason is rejected. A valid reason is trimmed and stored in the history with who made the change.

**Resolve permission**
- The assignee can resolve. Another agent, any agent on an unassigned ticket, and the ticket's creator all get 403.
- Reassigning a ticket moves the right to resolve to the new assignee.
- The permission check runs before the transition check: a non-assignee gets 403, not a 400 that reveals the transition rules.

**Concurrency**
- Stale version → 409 with "your version 1, current version 2". The first writer's change survives and the stale request writes nothing.
- A stale client gets "reload" (409) before any transition error.
- Retrying with a fresh version succeeds.
- Comments never conflict and don't bump the version.
- **Deterministic DB-level race:** two sessions both read v1, A commits, B's `UPDATE … WHERE version = 1` matches 0 rows → `VersionConflict`.
- **Real parallel HTTP race**, run 5 times: two threads are released together by a `threading.Barrier`, one resolving and one reassigning, both sending version 1. The result is always exactly `[200, 409]`. The final row reflects only the winner, and the loser's history row was rolled back too.

## 4. Do the tests actually catch bugs?

Passing tests only matter if they fail when the code is wrong. Each rule was switched off in memory in turn (no files edited) and the suite re-run:

| Rule disabled | Tests that failed |
|---|---|
| Only the assignee may resolve (`ensure_can_change_status`) | 8 |
| Allowed transitions (every move permitted) | 12 |
| Reopen reason required | 6 |
| Ticket privacy (`can_view_ticket`) | 4 |
| Version check, layer 1 (`ensure_version_matches`) | 4 |

With layer 1 disabled, the stale-client tests fail, but **the parallel race tests still pass**. Layer 2 (`version_id_col`) catches those writes on its own. This shows that each layer independently prevents silent overwrites.

## 5. File map

```
backend/
  pytest.ini                       testpaths, pythonpath
  tests/
    conftest.py                    engine/schema guard, truncate, client, users, make_ticket, auth()
    test_rules.py                  pure unit tests of rules.py
    test_auth_privacy.py           login, tokens, privacy, role permissions, validation
    test_status_transitions.py     lifecycle, disallowed moves, reopen reason, history
    test_resolve_permission.py     assigned-agent rule
    test_concurrency.py            stale version, DB-level race, parallel HTTP race
    test_tickets_list.py           pagination, filters, search
```
