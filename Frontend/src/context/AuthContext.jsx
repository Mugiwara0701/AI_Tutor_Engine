// src/context/AuthContext.jsx
// Placeholder for AuthContext — implement component/logic here.

import { createContext, useCallback, useMemo, useState } from "react";
import { mockLogin, mockSignUp } from "../features/auth/api/mockAuth.js";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const login = useCallback(async (credentials) => {
    setIsLoading(true);
    setError(null);
    try {
      const loggedInUser = await mockLogin(credentials);
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
      const newUser = await mockSignUp(details);
      setUser(newUser);
      return newUser;
    } catch (err) {
      setError(err.message || "Unable to create account.");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, error, login, signUp, logout }),
    [user, isLoading, error, login, signUp, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
