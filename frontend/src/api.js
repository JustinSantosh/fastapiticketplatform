// Thin wrapper around fetch for the FastAPI backend.
//  - adds the JWT to every request
//  - turns the backend's {detail, code, errors} body into an ApiError
//  - on 401, tells AuthContext so it can log the user out

const TOKEN_KEY = "ssd_token";

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.detail || `Request failed (${status})`);
    this.status = status;
    this.code = body?.code || "error";
    // { title: "String should have at least 3 characters", ... } for 422s
    this.fieldErrors = Object.fromEntries((body?.errors || []).map((e) => [e.field, e.message]));
  }
}

let unauthorizedHandler = () => {};
export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request(path, { method = "GET", body, params, signal } = {}) {
  const url = new URL(`/api${path}`, window.location.origin);
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });

  const headers = { Accept: "application/json" };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, { detail: "Cannot reach the server. Is the backend running?", code: "network_error" });
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    // A 401 on login just means bad credentials; elsewhere the session has ended.
    if (response.status === 401 && path !== "/auth/login") unauthorizedHandler();
    throw new ApiError(response.status, data);
  }
  return data;
}

export const api = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  me: () => request("/auth/me"),

  listTickets: (params, signal) => request("/tickets", { params, signal }),
  getTicket: (id, signal) => request(`/tickets/${id}`, { signal }),
  createTicket: (data) => request("/tickets", { method: "POST", body: data }),
  changeStatus: (id, status, version, reason) =>
    request(`/tickets/${id}/status`, { method: "POST", body: { status, version, reason: reason || null } }),
  assign: (id, assigneeId, version) =>
    request(`/tickets/${id}/assign`, { method: "POST", body: { assignee_id: assigneeId, version } }),
  addComment: (id, body) => request(`/tickets/${id}/comments`, { method: "POST", body: { body } }),

  listAgents: () => request("/users/agents"),
};
