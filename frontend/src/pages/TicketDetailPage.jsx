import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Alert, Field, Modal, PriorityBadge, Spinner, StatusBadge } from "../components/ui";
import { LIMITS, NEXT_STATUSES, STATUS_LABEL, actionLabel, formatDate, timeAgo } from "../lib/tickets";

export default function TicketDetailPage() {
  const { id } = useParams();
  const { user, isAgent } = useAuth();
  const location = useLocation();

  const [ticket, setTicket] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [notice, setNotice] = useState(location.state?.flash ? { kind: "success", text: location.state.flash } : null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(null); // which action is in flight, to show its spinner
  const [reopenOpen, setReopenOpen] = useState(false);

  const load = useCallback(
    (signal) =>
      api
        .getTicket(id, signal)
        .then((t) => {
          setTicket(t);
          setLoadError(null);
          setConflict(false);
        })
        .catch((err) => err.name !== "AbortError" && setLoadError(err)),
    [id]
  );

  useEffect(() => {
    const controller = new AbortController();
    setTicket(null);
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  // Every ticket edit goes through here: sends the version we loaded, and turns
  // a 409 into the "someone else changed this" banner instead of a generic error.
  async function mutate(name, request, successText) {
    setBusy(name);
    setNotice(null);
    try {
      setTicket(await request());
      setConflict(false);
      setNotice({ kind: "success", text: successText });
      return true;
    } catch (err) {
      if (err.status === 409) setConflict(true);
      else setNotice({ kind: "error", text: err.message });
      return false;
    } finally {
      setBusy(null);
    }
  }

  if (loadError) {
    return (
      <div className="empty">
        <h1>{loadError.status === 404 ? "Ticket not found" : "Couldn't load ticket"}</h1>
        <p>{loadError.status === 404 ? "It doesn't exist, or you don't have access to it." : loadError.message}</p>
        <Link to="/" className="btn btn-secondary">
          Back to tickets
        </Link>
      </div>
    );
  }
  if (!ticket) {
    return (
      <div className="empty">
        <Spinner label="Loading ticket" />
      </div>
    );
  }

  const changeStatus = (to, reason) =>
    mutate(
      `status-${to}`,
      () => api.changeStatus(ticket.id, to, ticket.version, reason),
      `Status changed to ${STATUS_LABEL[to]}.`
    );

  return (
    <>
      <Link to="/" className="back-link">
        ← Back to tickets
      </Link>

      {conflict && (
        <Alert
          kind="warning"
          action={
            <button className="btn btn-secondary" onClick={() => load()}>
              Reload ticket
            </button>
          }
        >
          <strong>This ticket was changed by someone else</strong> while you were viewing it. Your change was not
          saved. Reload to see the latest version, then try again.
        </Alert>
      )}
      {notice && <Alert kind={notice.kind}>{notice.text}</Alert>}

      <div className="detail-grid">
        <div>
          <div className="card">
            <div className="card-body">
              <div className="detail-title">
                <h1>
                  <span className="ticket-id">#{ticket.id}</span> {ticket.title}
                </h1>
                <StatusBadge status={ticket.status} />
              </div>
              <p className="description">{ticket.description}</p>
            </div>
          </div>

          <Comments
            ticket={ticket}
            onAdded={(c) => setTicket((t) => ({ ...t, comments: [...t.comments, c] }))}
          />
        </div>

        <aside>
          <div className="card">
            <div className="card-body">
              <dl className="meta">
                <div>
                  <dt>Priority</dt>
                  <dd>
                    <PriorityBadge priority={ticket.priority} />
                  </dd>
                </div>
                <div>
                  <dt>Raised by</dt>
                  <dd>{ticket.creator.id === user.id ? "You" : ticket.creator.full_name}</dd>
                </div>
                <div>
                  <dt>Assignee</dt>
                  <dd>{ticket.assignee?.full_name || <span className="muted">Unassigned</span>}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd title={ticket.created_at}>{formatDate(ticket.created_at)}</dd>
                </div>
              </dl>
            </div>
          </div>

          {isAgent && (
            <AgentActions
              ticket={ticket}
              user={user}
              busy={busy}
              onAssign={(assigneeId) =>
                mutate(
                  "assign",
                  () => api.assign(ticket.id, assigneeId, ticket.version),
                  assigneeId ? "Ticket assigned." : "Ticket unassigned."
                )
              }
              onStatus={(to) => (ticket.status === "resolved" ? setReopenOpen(true) : changeStatus(to))}
            />
          )}

          <History changes={ticket.status_changes} />
        </aside>
      </div>

      {reopenOpen && (
        <ReopenDialog
          busy={busy === "status-in_progress"}
          onCancel={() => setReopenOpen(false)}
          onConfirm={async (reason) => {
            const ok = await changeStatus("in_progress", reason);
            setReopenOpen(false);
            return ok;
          }}
        />
      )}
    </>
  );
}

function AgentActions({ ticket, user, busy, onAssign, onStatus }) {
  const [agents, setAgents] = useState([]);
  useEffect(() => {
    api.listAgents().then(setAgents).catch(() => setAgents([]));
  }, []);

  const isAssignee = ticket.assignee?.id === user.id;

  return (
    <div className="card">
      <div className="card-body">
        <h2 style={{ marginBottom: 14 }}>Actions</h2>
        <div className="actions">
          <Field label="Assigned agent" htmlFor="assignee">
            <select
              id="assignee"
              value={ticket.assignee?.id ?? ""}
              disabled={busy === "assign"}
              onChange={(e) => onAssign(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Unassigned</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.full_name}
                  {a.id === user.id ? " (you)" : ""}
                </option>
              ))}
            </select>
          </Field>
          {!isAssignee && (
            <button className="btn btn-secondary" disabled={!!busy} onClick={() => onAssign(user.id)}>
              {busy === "assign" && <Spinner />}Assign to me
            </button>
          )}

          {NEXT_STATUSES[ticket.status].map((to) => {
            // Mirrors rules.py so the button is explained up front; the server enforces it regardless.
            const blocked = to === "resolved" && !isAssignee;
            return (
              <div key={to}>
                <button
                  className={`btn ${to === "resolved" ? "btn-primary" : "btn-secondary"}`}
                  style={{ width: "100%" }}
                  disabled={!!busy || blocked}
                  onClick={() => onStatus(to)}
                >
                  {busy === `status-${to}` && <Spinner />}
                  {actionLabel(ticket.status, to)}
                </button>
                {blocked && (
                  <p className="hint" style={{ marginTop: 6 }}>
                    Only the assigned agent can resolve this ticket.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ReopenDialog({ busy, onCancel, onConfirm }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (!reason.trim()) return setError("A reason is required to reopen a resolved ticket");
    await onConfirm(reason.trim());
  }

  return (
    <Modal title="Reopen ticket" onClose={onCancel}>
      <p>The ticket goes back to In progress. Explain why, so the history shows it.</p>
      <form onSubmit={submit} noValidate>
        <Field label="Reason" htmlFor="reason" error={error}>
          <textarea
            id="reason"
            rows={4}
            value={reason}
            maxLength={LIMITS.reason.max}
            onChange={(e) => {
              setReason(e.target.value);
              setError("");
            }}
            autoFocus
          />
        </Field>
        <div className="form-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy && <Spinner />}Reopen
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Comments({ ticket, onAdded }) {
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!body.trim()) return setError("Write something first");
    setSending(true);
    setError("");
    try {
      onAdded(await api.addComment(ticket.id, body.trim()));
      setBody("");
    } catch (err) {
      setError(err.fieldErrors?.body || err.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="card">
      <div className="card-body">
        <div className="section-title">
          <h2>Comments</h2>
          <span className="muted">{ticket.comments.length}</span>
        </div>
        {ticket.comments.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No comments yet.
          </p>
        ) : (
          <ul className="comment-list">
            {ticket.comments.map((c) => (
              <li key={c.id} className="comment">
                <div className="comment-head">
                  <span className="comment-author">{c.author.full_name}</span>
                  {c.author.role === "agent" && <span className="role-tag role-agent">Agent</span>}
                  <span className="muted" title={formatDate(c.created_at)}>
                    {timeAgo(c.created_at)}
                  </span>
                </div>
                <p className="comment-body">{c.body}</p>
              </li>
            ))}
          </ul>
        )}
        <form className="comment-form" onSubmit={submit} noValidate>
          <Field label="Add a comment" htmlFor="comment" error={error}>
            <textarea
              id="comment"
              value={body}
              maxLength={LIMITS.comment.max}
              onChange={(e) => {
                setBody(e.target.value);
                setError("");
              }}
            />
          </Field>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={sending}>
              {sending && <Spinner />}Post comment
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function History({ changes }) {
  return (
    <div className="card">
      <div className="card-body">
        <h2 style={{ marginBottom: 14 }}>History</h2>
        {changes.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No status changes yet.
          </p>
        ) : (
          <ul className="timeline">
            {changes.map((h) => (
              <li key={h.id}>
                <strong>{h.changed_by.full_name}</strong> moved it from {STATUS_LABEL[h.from_status]} to{" "}
                {STATUS_LABEL[h.to_status]}
                <div className="muted" title={formatDate(h.created_at)}>
                  {timeAgo(h.created_at)}
                </div>
                {h.reason && <p className="reason">“{h.reason}”</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
