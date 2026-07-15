// src/router/RequireRole.jsx
//
// Gate a route to specific roles. Renders inside ProtectedRoute (so `user`
// is already guaranteed to exist) — this just adds a role check on top,
// e.g. keeping the "user" role out of Settings while admins/managers get
// through. Sits alongside the backend's own role checks (see
// app/auth/service.py / dependencies.py); this is a UX guard, not the
// security boundary.

import { Navigate } from "react-router-dom";
import { useAuth } from "../features/auth/hooks/useAuth.js";

export default function RequireRole({ roles, children }) {
  const { user } = useAuth();
  const role = (user?.role || "").trim().toLowerCase();

  if (!roles.includes(role)) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}
