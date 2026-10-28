import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Alert, Pagination, PriorityBadge, Spinner, StatusBadge } from "../components/ui";
import { timeAgo } from "../lib/tickets";

const PAGE_SIZE = 10;

export default function DashboardPage() {
  const { isAgent } = useAuth();
  const navigate = useNavigate();
  // Filters live in the URL, so they survive reloads and the back button.
  const [params, setParams] = useSearchParams();
  const filters = {
    status: params.get("status") || "",
    priority: params.get("priority") || "",
    assignee: params.get("assignee") || "",
    q: params.get("q") || "",
    page: Number(params.get("page")) || 1,
  };

  const [search, setSearch] = useState(filters.q);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  function setFilter(key, value) {
    const next = new URLSearchParams(params);
    value ? next.set(key, value) : next.delete(key);
    if (key !== "page") next.delete("page"); // new filter -> back to page 1
    setParams(next);
  }

  // Debounce the search box so we don't fire a request per keystroke.
  useEffect(() => {
    if (search === filters.q) return;
    const t = setTimeout(() => setFilter("q", search.trim()), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const queryKey = params.toString();
  useEffect(() => {
    const controller = new AbortController(); // cancel stale requests when filters change fast
    setLoading(true);
    setError(null);
    api
      .listTickets({ ...filters, page_size: PAGE_SIZE }, controller.signal)
      .then(setData)
      .catch((err) => err.name !== "AbortError" && setError(err))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, reloadKey]);

  const hasFilters = filters.status || filters.priority || filters.assignee || filters.q;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>{isAgent ? "All tickets" : "My tickets"}</h1>
          <p className="muted">
            {isAgent ? "Every ticket raised by users." : "Requests you've raised with the support team."}
          </p>
        </div>
        {!isAgent && (
          <Link to="/tickets/new" className="btn btn-primary">
            New ticket
          </Link>
        )}
      </div>

      <div className="card">
        <div className="filters" role="search">
          <input
            className="filter-search"
            type="search"
            placeholder="Search title or description…"
            aria-label="Search tickets"
            value={search}
            maxLength={100}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select aria-label="Status" value={filters.status} onChange={(e) => setFilter("status", e.target.value)}>
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="resolved">Resolved</option>
          </select>
          <select aria-label="Priority" value={filters.priority} onChange={(e) => setFilter("priority", e.target.value)}>
            <option value="">All priorities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          {isAgent ? (
            <select aria-label="Assignee" value={filters.assignee} onChange={(e) => setFilter("assignee", e.target.value)}>
              <option value="">Anyone</option>
              <option value="me">Assigned to me</option>
              <option value="unassigned">Unassigned</option>
            </select>
          ) : (
            <span />
          )}
          <button
            className="btn btn-ghost"
            disabled={!hasFilters}
            onClick={() => {
              setSearch("");
              setParams(new URLSearchParams());
            }}
          >
            Clear
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        {error ? (
          <div className="card-body">
            <Alert
              action={
                <button className="btn btn-secondary" onClick={() => setReloadKey((k) => k + 1)}>
                  Retry
                </button>
              }
            >
              Couldn't load tickets: {error.message}
            </Alert>
          </div>
        ) : !data ? (
          <div className="empty">
            <Spinner label="Loading tickets" />
          </div>
        ) : data.items.length === 0 ? (
          <div className="empty">
            <h2>{hasFilters ? "No tickets match these filters" : "No tickets yet"}</h2>
            <p>
              {hasFilters
                ? "Try a different search or clear the filters."
                : isAgent
                  ? "New tickets from users will show up here."
                  : "Raise your first request and the support team will pick it up."}
            </p>
            {!hasFilters && !isAgent && (
              <Link to="/tickets/new" className="btn btn-primary">
                New ticket
              </Link>
            )}
          </div>
        ) : (
          <>
            <table className={`ticket-table${loading ? " table-loading" : ""}`} aria-busy={loading}>
              <thead>
                <tr>
                  <th>Ticket</th>
                  <th>Status</th>
                  <th>Priority</th>
                  {isAgent && <th>Raised by</th>}
                  <th>Assignee</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.id} onClick={() => navigate(`/tickets/${t.id}`)}>
                    <td className="cell-title">
                      <span className="ticket-id">#{t.id}</span>{" "}
                      <Link className="ticket-title" to={`/tickets/${t.id}`} onClick={(e) => e.stopPropagation()}>
                        {t.title}
                      </Link>
                    </td>
                    <td data-label="Status">
                      <StatusBadge status={t.status} />
                    </td>
                    <td data-label="Priority">
                      <PriorityBadge priority={t.priority} />
                    </td>
                    {isAgent && <td data-label="Raised by">{t.creator.full_name}</td>}
                    <td data-label="Assignee">{t.assignee?.full_name || <span className="muted">Unassigned</span>}</td>
                    <td data-label="Created" className="muted" title={t.created_at}>
                      {timeAgo(t.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination
              page={data.page}
              pages={data.pages}
              total={data.total}
              onChange={(p) => setFilter("page", String(p))}
            />
          </>
        )}
      </div>
    </>
  );
}
