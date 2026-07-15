import EmployeeManagementSection from "../components/EmployeeManagementSection.jsx";
import ChangePasswordSection from "../components/ChangePasswordSection.jsx";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Manage workspace configuration and team access.
        </p>
      </div>

      <ChangePasswordSection />
      <EmployeeManagementSection />
    </div>
  );
}
