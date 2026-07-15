import { Navigate } from "react-router-dom";
import EmployeeManagementSection from "../components/EmployeeManagementSection.jsx";
import { useAuth } from "../../auth/hooks/useAuth.js";

export default function SettingsPage() {
  const { user } = useAuth();

  // Settings is admin/manager only — the Settings nav item is already
  // hidden in the sidebar for "user" accounts, but guard the route itself
  // too in case someone navigates here directly by URL.
  if (user?.role !== "admin" && user?.role !== "manager") {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Manage workspace configuration and team access.
        </p>
      </div>

      <EmployeeManagementSection />
    </div>
  );
}
