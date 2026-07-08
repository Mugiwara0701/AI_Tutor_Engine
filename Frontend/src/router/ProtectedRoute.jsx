// src/router/ProtectedRoute.jsx
// Placeholder for ProtectedRoute — implement component/logic here.

import { Navigate } from "react-router-dom";
import { useAuth } from "../features/auth/hooks/useAuth.js";

export default function ProtectedRoute({ children }) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
