import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedLayout } from "./components/Layout";
import CreateTicketPage from "./pages/CreateTicketPage";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import TicketDetailPage from "./pages/TicketDetailPage";
import "./styles.css";

function NotFound() {
  return (
    <div className="empty">
      <h1>Page not found</h1>
      <Link to="/">Back to tickets</Link>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/tickets/new" element={<CreateTicketPage />} />
            <Route path="/tickets/:id" element={<TicketDetailPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
