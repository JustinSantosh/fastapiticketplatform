# Smart Support Desk

A support-ticket app. **Users** raise tickets and comment on them; **agents** see every ticket, assign them, and move them through `Open → In Progress → Resolved`.

**Stack:** React 18 (Vite) · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · PostgreSQL · Alembic · JWT auth

| Doc | What's in it |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the frontend, backend and database fit together |
| [docs/DATABASE.md](docs/DATABASE.md) | Entities, relationships, constraints, indexes |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Technical decisions, trade-offs, assumptions |
| [docs/phases/](docs/phases/) | Build log, one file per phase |

---

## 1. Prerequisites

| Tool | Version used | Check |
|---|---|---|
| Python | 3.12 (3.11+ should work) | `python --version` |
| Node.js | 22 (18+ should work) | `node --version` |
| PostgreSQL | 17 (14+ should work) | pgAdmin, or `psql --version` |

## 2. Database

Create **one empty database** in pgAdmin (right-click *Databases → Create → Database*) or with psql:

```sql
CREATE DATABASE "Yalla & co";
```

Any name works, as long as `.env` matches it exactly (see below).

- The app's tables live in its `public` schema.
- The tests create their own throwaway tables in a separate `test` schema of the same database, so running tests never touches app data.

## 3. Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                # macOS/Linux: cp .env.example .env
```

Edit `backend/.env`:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:<password>@localhost:5432/Yalla & co` |
| `TEST_DATABASE_URL` | the same URL + `?options=-csearch_path%3Dtest` |
| `JWT_SECRET` | output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `JWT_EXPIRE_MINUTES` | `120` |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |

> **URL gotchas:**
> - The **database name** is written exactly as in pgAdmin. It is case-sensitive and must not be percent-encoded.
> - Special characters in the **password** *must* be percent-encoded: `@`→`%40`, `:`→`%3A`, `/`→`%2F`, `%`→`%25`, `#`→`%23`.

Create the tables and load demo data:

```powershell
alembic upgrade head          # runs the migrations in backend/alembic/versions
python -m scripts.seed        # 2 users, 2 agents, 3 sample tickets
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs. Log in via `POST /api/auth/login`, click **Authorize**, and paste the token.
- Health check: http://127.0.0.1:8000/api/health → `{"status":"ok","database":"ok"}`

## 4. Frontend setup

In a second terminal:

```powershell
cd frontend
npm ci              # installs the exact versions in package-lock.json
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api/*` to the backend on port 8000, so the backend must be running.

## 5. Demo accounts (demo only)

All use the password **`Password123!`**:

| Email | Role |
|---|---|
| alice@example.com | User |
| bob@example.com | User |
| agent.sam@example.com | Agent |
| agent.priya@example.com | Agent |

**A quick tour:**
1. Log in as **alice**. She sees only her own tickets; create one.
2. Log in as **bob** and paste the URL of Alice's ticket → "Ticket not found".
3. Log in as **agent.sam**. Open the ticket, click *Assign to me*, *Start progress*, then *Resolve*.
4. Log in as **agent.priya**. On Sam's ticket, *Resolve* is disabled; *Reopen* asks for a reason.
5. Open the same ticket in two tabs and change it in one. Acting in the other shows the conflict banner.

Reset the demo data at any time. This **deletes every row** in the app's tables and re-seeds:

```powershell
python -m scripts.seed --reset
```

## 6. Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest                    # 79 tests, ~10 s
pytest -v                 # one line per test
pytest tests/test_concurrency.py -v
```

- The tests use real PostgreSQL through `TEST_DATABASE_URL`, in the `test` schema.
- The fixture **refuses to run** if that URL equals `DATABASE_URL` or doesn't resolve to the `test` schema.
- Tables are created at the start of a run, truncated after every test, and dropped at the end, so runs are repeatable.

| Requirement from the brief | Test file |
|---|---|
| Authorization & user ticket privacy | `tests/test_auth_privacy.py` |
| Allowed / disallowed status transitions | `tests/test_rules.py`, `tests/test_status_transitions.py` |
| Assigned-agent permission to resolve | `tests/test_resolve_permission.py` |
| Concurrent update / conflict handling | `tests/test_concurrency.py` |
| Filtering & pagination | `tests/test_tickets_list.py` |

Details: [docs/phases/PHASE-4-tests.md](docs/phases/PHASE-4-tests.md).

## 7. Business rules and where they live

All rules are enforced on the server in [`backend/app/rules.py`](backend/app/rules.py) (pure functions) and called by [`backend/app/services.py`](backend/app/services.py). The UI only hides buttons as a convenience.

| Rule | Behaviour |
|---|---|
| Status transitions | Only `open→in_progress`, `in_progress→resolved`, `resolved→in_progress`. Anything else → **400** |
| Reopening | `resolved→in_progress` needs a non-blank `reason`, stored in the ticket history. Otherwise → **400** |
| Resolution permission | Only the ticket's assigned agent can resolve. Otherwise → **403** |
| Ticket privacy | Users only see their own tickets. Others' tickets → **404**, indistinguishable from "doesn't exist" |
| Concurrent updates | Every edit sends the `version` it loaded. Stale version, or losing a race at the DB → **409**; nothing is overwritten |

## 8. Project layout

```
backend/
  app/
    main.py          app, CORS, routers, error handlers
    config.py        settings from .env
    db.py            engine, session, Base
    models.py        SQLAlchemy models
    schemas.py       Pydantic request/response models
    rules.py         business rules (pure)
    auth.py          bcrypt, JWT, get_current_user
    services.py      use-cases (DB + rules)
    routers/         HTTP endpoints
  alembic/           migrations
  scripts/seed.py    demo data
  tests/             pytest suite
frontend/
  src/
    api.js           fetch wrapper
    auth/            AuthContext
    pages/           Login, Dashboard, CreateTicket, TicketDetail
    components/      layout + UI pieces
    styles.css
docs/
```

## 9. Assumptions

- **Only users create tickets**; agents work on them.
- **Only agents change status or assignment.** A ticket's creator cannot reopen it; they comment instead.
- **Any agent can start or reopen a ticket**, but only the **assigned** agent can resolve it. A ticket must therefore be assigned before it can be resolved.
- Only agents can be assignees. A ticket can be reassigned or unassigned by any agent.
- **Agents can comment on any ticket**; users only on their own.
- There is no self-registration. Accounts come from the seed script.

## 10. Known limitations

These are stated honestly:

- **No frontend automated tests.** The backend has 79 tests; the UI was verified manually in the browser (see [PHASE-5](docs/phases/PHASE-5-frontend.md)).
- **Tickets can't be edited after creation** (title, description, priority), and comments can't be edited or deleted. The brief doesn't require it.
- **JWT is stored in `localStorage`.** There are no refresh tokens, and a token can't be revoked before it expires (120 minutes). See [DECISIONS.md](docs/DECISIONS.md).
- **No user management UI**, password reset, or login rate limiting.
- **No live updates.** A conflicting edit is detected when you save (409 + banner), not pushed to you while you're viewing.
- The search uses `ILIKE`, which is fine at this scale. A large dataset would need a trigram or full-text index.
- Deployment is not included; the app is meant to run locally as described above.
