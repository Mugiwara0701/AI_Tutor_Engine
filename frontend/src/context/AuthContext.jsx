// src/context/AuthContext.jsx

import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  loginUser,
  signUpUser,
  logoutUser,
  fetchCurrentUser,
} from "../features/auth/api/authApi.js";
import { getStoredToken, setStoredToken } from "../lib/apiClient.js";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(false); // login/signup in flight
  const [isRestoring, setIsRestoring] = useState(true); // initial session check on page load
  const [error, setError] = useState(null);

  // On first load, if a token is already stored (from a previous session),
  // try to fetch the current user to restore the session without
  // requiring the person to log in again.
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      const token = getStoredToken();
      if (!token) {
        setIsRestoring(false);
        return;
      }
      try {
        const restoredUser = await fetchCurrentUser();
        if (!cancelled) setUser(restoredUser);
      } catch {
        // Token invalid/expired — clear it silently and require fresh login.
        setStoredToken(null);
      } finally {
        if (!cancelled) setIsRestoring(false);
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (credentials) => {
    setIsLoading(true);
    setError(null);
    try {
      const loggedInUser = await loginUser(credentials);
      setUser(loggedInUser);
      return loggedInUser;
    } catch (err) {
      setError(err.message || "Unable to sign in.");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const signUp = useCallback(async (details) => {
    setIsLoading(true);
    setError(null);
    try {
      const newUser = await signUpUser(details);
      setUser(newUser);
      return newUser;
    } catch (err) {
      setError(err.message || "Unable to create account.");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } catch {
      // Best-effort — clear local session regardless of API outcome.
    } finally {
      setStoredToken(null);
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, isRestoring, error, login, signUp, logout }),
    [user, isLoading, isRestoring, error, login, signUp, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
