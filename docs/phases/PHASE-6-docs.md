# Phase 6: Documentation and Submission Polish

**Goal:** cover every item in the brief's deliverables checklist, and prove the README works from a clean start.

## 1. Deliverables checklist (from the brief)

| # | Deliverable | Where |
|---|---|---|
| 01 | GitHub repository, clearly organized | Repo root; layout in README §8. *Not pushed yet; see "Remaining steps".* |
| 02 | README: prerequisites, env config, DB setup/migrations, run, test commands | [README.md](../../README.md) §1–§6 |
| 03 | Architecture overview | [docs/ARCHITECTURE.md](../ARCHITECTURE.md) |
| 04 | Database design: entities, relationships, constraints | [docs/DATABASE.md](../DATABASE.md) |
| 05 | Technical decisions: permissions, transitions, concurrency | [docs/DECISIONS.md](../DECISIONS.md) §3–§5 |
| 06 | Automated tests + instructions | `backend/tests/` (79 tests) + README §6 |
| — | No secrets committed; example env file | `.env` is git-ignored; [backend/.env.example](../../backend/.env.example) uses placeholders |
| — | Assumptions and known limitations stated honestly | README §9–§10, DECISIONS §11–§12 |

## 2. Added in this phase

- `README.md`: setup on a clean machine, demo accounts, a 5-step tour of the rules, test commands, a rules table, the project layout, assumptions and limitations.
- `docs/ARCHITECTURE.md`: the tiers, backend layers, a request lifecycle, the auth sequence diagram, frontend structure, and the dev topology.
- `docs/DATABASE.md`: ER diagram, entities, relationships with their `ON DELETE` reasons, constraints (DB vs API vs code), indexes, the `version` column.
- `docs/DECISIONS.md`: FastAPI vs Django, layering, permissions (404 vs 403, check order), transitions, optimistic vs pessimistic locking, JWT storage trade-offs, validation layers, testing approach, assumptions, what I'd do next.
- `scripts/seed.py --reset`: wipes the app tables and re-seeds the demo data.

## 3. Clean-setup check

Only the files git would commit were copied to a fresh folder: no `.env`, `.venv` or `node_modules`. The README was then followed from scratch. To avoid touching real data, the copy's `DATABASE_URL` pointed at a temporary `setup_check` schema.

| Step | Result |
|---|---|
| `python -m venv .venv` + `pip install -r requirements.txt` | OK |
| `.env` from `.env.example` (only the password and secret filled in) | OK |
| `alembic upgrade head` | `Running upgrade -> 8a59d62bb307, initial schema` |
| `python -m scripts.seed` | 4 users, 3 tickets |
| `python -m scripts.seed --reset` | wiped and re-seeded |
| `pytest` | **79 passed** |
| `/api/health`, login as agent.sam | `database: ok`, 200, sees 3 tickets |
| `npm ci` + `npm run build` | 65 packages, built |
| Afterwards | `public` unchanged (4 users / 4 tickets); `setup_check` and `test` schemas dropped; temp copy deleted |

## 4. Remaining steps (yours)

1. **Commit and push** to a GitHub repository, and make sure the reviewers can access it.
2. Optionally, run `python -m scripts.seed --reset` before demoing, for a clean set of 3 sample tickets.
3. Before the interview, read through `rules.py`, `services.py` and `test_concurrency.py`. Those are what the reviewers will most likely ask about or ask you to change live.

### Changes a reviewer is likely to ask for live

| Change | Where to make it |
|---|---|
| "Let the ticket creator reopen their own ticket" | `rules.ensure_can_change_status` + a test |
| "Add a *Closed* status after Resolved" | `models.Status`, `rules.ALLOWED_TRANSITIONS`, a new Alembic migration (VARCHAR + CHECK makes this easy), `lib/tickets.js` labels |
| "Require an assignee before *Start progress*" | `rules.ensure_can_change_status` (or `validate_transition`) + a test |
| "Let agents filter by creator" | `TicketFilters` + `list_tickets` in the service, a query param in the router, a select on the Dashboard |
| "Make the page size 20" | `PAGE_SIZE` in `DashboardPage.jsx` (the server allows up to 100) |
