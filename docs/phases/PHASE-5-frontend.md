# Phase 5: React Frontend

**Goal:** the four required screens (Login, Dashboard, Create Ticket, Ticket Details), responsive and with validation, loading states, error handling and clear feedback. The stack stays minimal: React + react-router + plain CSS, with no UI library.

## 1. Run it

```powershell
# terminal 1: API
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload

# terminal 2: UI
cd frontend
npm install        # first time only
npm run dev        # http://localhost:5173
```

The Vite dev server **proxies `/api/*` to `http://127.0.0.1:8000`**, so the browser talks to one origin.

## 2. Structure

```
frontend/
  index.html
  vite.config.js            dev server + /api proxy
  src/
    main.jsx                routes
    api.js                  fetch wrapper: JWT header, ApiError, 401 → session end
    auth/AuthContext.jsx    current user, login/logout, session-expired handling
    lib/tickets.js          labels, date helpers, LIMITS, UI copy of the transition map
    components/
      Layout.jsx            top bar + auth guard (ProtectedLayout)
      ui.jsx                StatusBadge, PriorityBadge, Spinner, Alert, Field, Modal, Pagination
    pages/
      LoginPage.jsx
      DashboardPage.jsx
      CreateTicketPage.jsx
      TicketDetailPage.jsx  + AgentActions, ReopenDialog, Comments, History
    styles.css              design tokens (light + dark), components, responsive rules
```

## 3. Screens

| Screen | What it does |
|---|---|
| **Login** | Client-side checks (required fields, email format). Shows the server's generic "Invalid email or password". Spinner on the button while signing in. Demo-account shortcuts fill the form. Shows a "session expired" notice when the server ended the session. |
| **Dashboard** | Users see "My tickets"; agents see "All tickets" plus a *Raised by* column and an *Assignee* filter (me / unassigned). Search is debounced (350 ms). Status and priority filters, Clear, Previous/Next pagination with "Page x of y · n tickets". **Filters live in the URL** (`/?status=open&page=2`), so reload, back/forward and shared links all work. In-flight requests are cancelled (`AbortController`) when filters change, so a slow old response can't overwrite a newer one. Separate states for loading, empty, "no matches", and error with Retry. |
| **Create ticket** | Users only; agents are redirected (and the API would return 403 anyway). Title, description (with a character counter) and priority. Client rules mirror the Pydantic limits. Server 422 field errors appear under the matching inputs. On success it goes to the new ticket with a "Ticket created" message. |
| **Ticket details** | Title, status badge, description, priority, creator, assignee, created date. Comment thread and add-comment form. Status history timeline that shows **reopen reasons**. Agents also get an **Actions** panel: an assign dropdown, "Assign to me", and buttons for the next allowed status only. *Resolve* is disabled with an explanation for non-assignees. *Reopen* opens a dialog that requires a reason. "Not found / no access" is one message, matching the backend's 404. |

## 4. How it talks to the backend

### `api.js`
- Adds `Authorization: Bearer <token>` to every request.
- Turns error bodies into `ApiError { status, code, message, fieldErrors }`. `fieldErrors` is `{title: "…"}`, built from the backend's 422 `errors` list.
- Turns a network failure into a readable "Cannot reach the server" message.
- On **401** from any endpoint except login, calls `onUnauthorized`, which logs the user out.

### Optimistic locking in the UI
Every edit sends back the `version` from the last ticket it loaded:

```js
api.changeStatus(ticket.id, to, ticket.version, reason)
api.assign(ticket.id, assigneeId, ticket.version)
```

A successful response returns the updated ticket (with a new version), which replaces local state. A **409** shows a warning banner: *"This ticket was changed by someone else… Your change was not saved. Reload to see the latest version."* The page doesn't reload silently, so the user knows their action didn't happen.

### The UI never enforces rules
`lib/tickets.js` holds a copy of the transition map and the length limits. It's used only to decide which buttons to show and to give instant feedback. The backend re-checks everything. For example, the disabled Resolve button is a hint, but calling the API directly still returns 403.

### Token storage (trade-off)
The JWT lives in `localStorage`. That's simple and survives a page reload, but any XSS bug could read it. The alternative is an httpOnly cookie, which JavaScript can't read but which needs CSRF protection and a cookie-aware CORS setup. React escapes all rendered text and the app never uses `dangerouslySetInnerHTML`, so localStorage is an acceptable trade-off here. The short expiry (120 minutes) limits the damage if a token leaks.

## 5. Design

- Plain CSS with **design tokens** in `:root` (colors, radius, shadow), redefined under `prefers-color-scheme: dark`, so dark mode follows the OS.
- Status colors: Open = blue, In progress = amber, Resolved = green. Priority uses a colored dot plus text, so it doesn't depend on color alone.
- **Responsive:**
  - At ≤860px the details page goes to one column.
  - At ≤640px the ticket table becomes stacked cards. This is the *same* `<table>` markup with CSS labels (`td::before { content: attr(data-label) }`).
  - At ≤640px the filters stack and the user's name hides in the top bar.

  Verified at 375px wide with no horizontal scroll.
- **Accessibility:**
  - real `<label>`s
  - `aria-invalid` and `aria-describedby` linking inputs to their errors
  - `role="alert"` on errors and `role="status"` on spinners
  - a native `<dialog>` for the reopen modal, which gives focus trapping and Esc to close
  - visible focus rings, and reduced motion respected

## 6. Verified in the browser

These checks ran against the real backend and the `Yalla & co` database:

| Check | Result |
|---|---|
| Empty login submit | "Email is required" / "Password is required" |
| Wrong password | "Invalid email or password" |
| Alice logs in | Dashboard "My tickets" shows only her 2 tickets |
| Create with a 2-character title and no description | Both field errors shown, nothing sent |
| Valid create (High) | Redirected to `/tickets/5` with "Ticket created" |
| Bob opens `/tickets/5` | "Ticket not found. It doesn't exist, or you don't have access to it." |
| Priya (agent) opens Sam's ticket #2 | Sees all tickets; Resolve disabled with "Only the assigned agent can resolve this ticket" |
| **Conflict:** #5 open in two tabs, tab 2 "Assign to me", then tab 1 "Start progress" | Tab 1 shows the "changed by someone else" banner; nothing saved; Reload fixes it |
| Lifecycle: start, then resolve | Success notices, status badge updates |
| Reopen with an empty reason | "A reason is required to reopen a resolved ticket" |
| Reopen with a reason, then comment | History shows 3 moves with the reason quoted; comment appears |
| `/?assignee=me&status=in_progress` | Exactly ticket #5 |
| Search with no matches | "No tickets match these filters" |
| 375px viewport | Cards layout, no horizontal overflow |

### Bugs found and fixed during this check
1. **Logging out and back in as someone else went to the previous person's page.** "Return to where you were" applied to deliberate logouts too. It now applies only when the *server* ended the session (`sessionExpired` in `AuthContext`), and the login page says "Your session has expired" in that case.
2. **The top bar wrapped on phones.** The user's name is now hidden at ≤640px (the role tag stays).

Note: this check created ticket #5 (with its history and a comment) in the real database. Reset the demo data at any time with the commands in the Phase 6 README, or keep it as demo content.
