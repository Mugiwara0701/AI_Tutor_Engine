// src/router/ProtectedRoute.jsx

import { Navigate } from "react-router-dom";
import { useAuth } from "../features/auth/hooks/useAuth.js";

export default function ProtectedRoute({ children }) {
  const { user, isRestoring } = useAuth();

  // Still checking whether a stored token corresponds to a valid session
  // (e.g. right after a page refresh) — avoid a flash-redirect to /login.
  if (isRestoring) {
    return (
      <div className="flex items-center justify-center h-screen text-sm text-slate-400">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
