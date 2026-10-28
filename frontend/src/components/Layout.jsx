import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Spinner } from "./ui";

// Wraps every logged-in page: redirects to /login if there's no session.
// (Convenience only - the API rejects unauthenticated requests on its own.)
export function ProtectedLayout() {
  const { user, ready, isAgent, sessionExpired, logout } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="page-center">
        <Spinner label="Checking session" />
      </div>
    );
  }
  if (!user) {
    // After a deliberate logout, the next person starts fresh on the dashboard.
    return <Navigate to="/login" replace state={sessionExpired ? { from: location } : undefined} />;
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/" className="brand">
            <span className="brand-mark" aria-hidden="true" />
            Support Desk
          </Link>
          <div className="topbar-user">
            <span className="user-name">
              <span className="name-text">{user.full_name}</span>
              <span className={`role-tag role-${user.role}`}>{isAgent ? "Agent" : "User"}</span>
            </span>
            <button className="btn btn-ghost" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}
