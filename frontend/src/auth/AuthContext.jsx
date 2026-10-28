import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, onUnauthorized, tokenStore } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // "checking" while we validate a token left over from a previous visit
  const [status, setStatus] = useState(tokenStore.get() ? "checking" : "ready");
  // true when the server ended the session (expired/invalid token), as opposed
  // to the user clicking "Log out" - only then do we offer to return them to their page.
  const [sessionExpired, setSessionExpired] = useState(false);

  const logout = useCallback(() => {
    tokenStore.clear();
    setSessionExpired(false);
    setUser(null);
  }, []);

  const expire = useCallback(() => {
    tokenStore.clear();
    setSessionExpired(true);
    setUser(null);
  }, []);

  useEffect(() => {
    onUnauthorized(expire); // any 401 from the API ends the session
    if (!tokenStore.get()) return;
    api
      .me()
      .then(setUser)
      .catch(() => expire())
      .finally(() => setStatus("ready"));
  }, [expire]);

  const login = useCallback(async (email, password) => {
    const { access_token, user: loggedIn } = await api.login(email, password);
    tokenStore.set(access_token);
    setSessionExpired(false);
    setUser(loggedIn);
    return loggedIn;
  }, []);

  const value = {
    user,
    isAgent: user?.role === "agent",
    ready: status === "ready",
    sessionExpired,
    login,
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
