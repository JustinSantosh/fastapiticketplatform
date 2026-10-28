import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Alert, Field, Spinner } from "../components/ui";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Seeded demo accounts (backend/scripts/seed.py). Demo only.
const DEMO = [
  ["alice@example.com", "User"],
  ["bob@example.com", "User"],
  ["agent.sam@example.com", "Agent"],
  ["agent.priya@example.com", "Agent"],
];

function validate({ email, password }) {
  const errors = {};
  if (!email.trim()) errors.email = "Email is required";
  else if (!EMAIL_RE.test(email.trim())) errors.email = "Enter a valid email address";
  if (!password) errors.password = "Password is required";
  return errors;
}

export default function LoginPage() {
  const { user, login, sessionExpired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

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
      await login(form.email.trim(), form.password);
      navigate(location.state?.from?.pathname || "/", { replace: true });
    } catch (err) {
      setServerError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="page-center">
      <div className="card login-card">
        <div className="card-body">
          <div className="login-head">
            <div className="brand">
              <span className="brand-mark" aria-hidden="true" />
              Support Desk
            </div>
            <h1>Sign in</h1>
            <p className="muted">Track and resolve support requests.</p>
          </div>

          {serverError && <Alert>{serverError}</Alert>}
          {!serverError && sessionExpired && (
            <Alert kind="warning">Your session has expired. Please sign in again.</Alert>
          )}

          <form onSubmit={onSubmit} noValidate>
            <Field label="Email" htmlFor="email" error={errors.email}>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={form.email}
                onChange={update("email")}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "email-error" : undefined}
                autoFocus
              />
            </Field>
            <Field label="Password" htmlFor="password" error={errors.password}>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={form.password}
                onChange={update("password")}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "password-error" : undefined}
              />
            </Field>
            <button className="btn btn-primary" type="submit" disabled={submitting} style={{ width: "100%" }}>
              {submitting && <Spinner label="Signing in" />}
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="demo-accounts">
            <span className="muted">Demo accounts (password: Password123!)</span>
            <ul>
              {DEMO.map(([email, role]) => (
                <li key={email}>
                  <button type="button" onClick={() => setForm({ email, password: "Password123!" })}>
                    {email}
                  </button>{" "}
                  <span className="muted">· {role}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
