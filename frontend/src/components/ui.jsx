// Small presentational building blocks shared by the pages.
import { useEffect, useRef } from "react";
import { PRIORITY_LABEL, STATUS_LABEL } from "../lib/tickets";

export function StatusBadge({ status }) {
  return <span className={`badge status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function PriorityBadge({ priority }) {
  return (
    <span className={`priority priority-${priority}`}>
      <span className="priority-dot" aria-hidden="true" />
      {PRIORITY_LABEL[priority]}
    </span>
  );
}

export function Spinner({ label = "Loading" }) {
  return (
    <span className="spinner" role="status">
      <span className="visually-hidden">{label}</span>
    </span>
  );
}

export function Alert({ kind = "error", children, action }) {
  return (
    <div className={`alert alert-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <div>{children}</div>
      {action}
    </div>
  );
}

export function Field({ label, htmlFor, error, hint, children }) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? (
        <p className="field-error" id={`${htmlFor}-error`}>
          {error}
        </p>
      ) : (
        hint && <p className="field-hint">{hint}</p>
      )}
    </div>
  );
}

export function Modal({ title, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal(); // native <dialog>: focus trap + Esc handling for free
    return () => dialog.close();
  }, []);
  return (
    <dialog ref={ref} className="modal" onCancel={onClose} aria-labelledby="modal-title">
      <h2 id="modal-title">{title}</h2>
      {children}
    </dialog>
  );
}

export function Pagination({ page, pages, total, onChange }) {
  if (total === 0) return null;
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="muted">
        Page {page} of {pages} · {total} ticket{total === 1 ? "" : "s"}
      </span>
      <div className="pagination-buttons">
        <button className="btn btn-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          Previous
        </button>
        <button className="btn btn-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          Next
        </button>
      </div>
    </nav>
  );
}
