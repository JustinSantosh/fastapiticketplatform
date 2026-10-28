import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Alert, Field, Spinner } from "../components/ui";
import { LIMITS } from "../lib/tickets";

// Client-side checks mirror backend/app/schemas.py for instant feedback.
// The server re-validates everything; its 422 field errors are shown the same way.
function validate({ title, description }) {
  const errors = {};
  const t = title.trim();
  const d = description.trim();
  if (t.length < LIMITS.title.min) errors.title = `Title must be at least ${LIMITS.title.min} characters`;
  else if (t.length > LIMITS.title.max) errors.title = `Title must be at most ${LIMITS.title.max} characters`;
  if (d.length < LIMITS.description.min) errors.description = "Please describe the problem";
  else if (d.length > LIMITS.description.max)
    errors.description = `Description must be at most ${LIMITS.description.max} characters`;
  return errors;
}

export default function CreateTicketPage() {
  const { isAgent } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ title: "", description: "", priority: "medium" });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isAgent) return <Navigate to="/" replace />; // UI nicety; the API returns 403 anyway

  const update = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    setErrors((errs) => ({ ...errs, [key]: undefined }));
  };

  async function onSubmit(e) {
    e.preventDefault();
    const found = validate(form);
    setErrors(found);
    setServerError("");
    if (Object.keys(found).length) return;

    setSubmitting(true);
    try {
      const ticket = await api.createTicket({
        title: form.title.trim(),
        description: form.description.trim(),
        priority: form.priority,
      });
      navigate(`/tickets/${ticket.id}`, { state: { flash: "Ticket created. The support team has been notified." } });
    } catch (err) {
      setErrors(err.fieldErrors || {});
      setServerError(err.status === 422 ? "Please fix the highlighted fields." : err.message);
      setSubmitting(false);
    }
  }

  return (
    <>
      <Link to="/" className="back-link">
        ← Back to tickets
      </Link>
      <div className="page-header">
        <div>
          <h1>New ticket</h1>
          <p className="muted">Describe the problem and we'll get back to you.</p>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 720 }}>
        <form className="card-body" onSubmit={onSubmit} noValidate>
          {serverError && <Alert>{serverError}</Alert>}

          <Field label="Title" htmlFor="title" error={errors.title} hint="A short summary, e.g. “Can't log in to VPN”">
            <input
              id="title"
              value={form.title}
              onChange={update("title")}
              maxLength={LIMITS.title.max}
              aria-invalid={!!errors.title}
              aria-describedby={errors.title ? "title-error" : undefined}
              autoFocus
            />
          </Field>

          <Field
            label="Description"
            htmlFor="description"
            error={errors.description}
            hint={`${form.description.trim().length} / ${LIMITS.description.max} characters`}
          >
            <textarea
              id="description"
              rows={7}
              value={form.description}
              onChange={update("description")}
              maxLength={LIMITS.description.max}
              aria-invalid={!!errors.description}
              aria-describedby={errors.description ? "description-error" : undefined}
              placeholder="What happened? What did you expect? Any error messages?"
            />
          </Field>

          <Field label="Priority" htmlFor="priority" error={errors.priority}>
            <select id="priority" value={form.priority} onChange={update("priority")}>
              <option value="low">Low: minor inconvenience</option>
              <option value="medium">Medium: affects my work</option>
              <option value="high">High: I'm blocked</option>
            </select>
          </Field>

          <div className="form-actions">
            <Link to="/" className="btn btn-secondary">
              Cancel
            </Link>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting && <Spinner label="Creating ticket" />}
              {submitting ? "Creating…" : "Create ticket"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
