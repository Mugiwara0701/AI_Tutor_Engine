import { useAuth } from "../features/auth/hooks/useAuth.js";
import { Navigate } from "react-router-dom";
export default function ProtectedRoute({ children }) {
  const { user, isRestoring } = useAuth();

  if (isRestoring) {
    return (
      <div className="flex items-center justify-center h-screen bg-bgLight">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center animate-pulse">
            <span className="text-white font-bold text-sm">M</span>
          </div>
          <p className="text-sm text-slate-400">Loading your workspace…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
