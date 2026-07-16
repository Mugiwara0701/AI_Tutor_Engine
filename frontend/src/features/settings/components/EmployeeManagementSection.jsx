// src/features/settings/components/EmployeeManagementSection.jsx
//
// Employee / User Management. All create/read/update/delete actions call
// the FastAPI backend (see useEmployeeData / employeeApi.js), which is the
// only thing that talks to the database. Local React state just mirrors
// the backend's response so the table updates without a full refetch.
import { useState } from "react";
import { UserPlus, Users } from "lucide-react";
import { useEmployeeData } from "../hooks/useEmployeeData.js";
import EmployeeFormModal from "./EmployeeFormModal.jsx";
import EmployeeTable from "./EmployeeTable.jsx";
import InlineAlert from "../../../components/shared/InlineAlert.jsx";
import { registerUser } from "../../auth/api/authApi.js";
import { updateUserRecord } from "../api/employeeApi.js";
import { useAuth } from "../../auth/hooks/useAuth.js";
import { DEFAULT_EMPLOYEE_PASSWORD } from "../../../lib/constants.js";

// Which roles a given viewer is allowed to see in the employee list:
//   - admin can see everyone (admin, manager, user)
//   - manager can see other managers and users, but not admins
//   - user shouldn't reach this component at all (Settings is
//     admin/manager only — see SettingsPage.jsx), so default to nothing.
const VISIBLE_ROLES_BY_VIEWER = {
  admin: ["admin", "manager", "user"],
  manager: ["manager", "user"],
  user: [],
};

export default function EmployeeManagementSection() {
  const { user } = useAuth();
  const {
    employees,
    roleOptions,
    statusOptions,
    addEmployee,
    updateEmployee,
    deleteEmployee,
    toggleStatus,
    isUserIdTaken,
  } = useEmployeeData();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [alert, setAlert] = useState(null);

  const canAddEmployee = user?.role === "admin";
  const visibleRoles = VISIBLE_ROLES_BY_VIEWER[user?.role] ?? [];
  const visibleEmployees = employees.filter((emp) =>
    visibleRoles.includes(emp.role),
  );
  // A manager editing a visible row shouldn't be able to promote them to
  // admin via the role dropdown — only offer roles the viewer can grant.
  const assignableRoleOptions = roleOptions.filter((role) =>
    visibleRoles.includes(role),
  );

  const openAddModal = () => {
    setEditingEmployee(null);
    setModalOpen(true);
  };

  const openEditModal = (employee) => {
    setEditingEmployee(employee);
    setModalOpen(true);
  };

  const handleSubmit = async (form) => {
    if (editingEmployee) {
      await updateEmployee(editingEmployee.id, form);
      setAlert({
        type: "success",
        message: `${form.name}'s details were updated.`,
      });
      setModalOpen(false);
      setEditingEmployee(null);
      return;
    }

    // Register the new employee against the real backend, using the same
    // fixed default password for every account created here. The backend
    // always creates new accounts as role="user" / Active — it has no way
    // to accept a role at signup, by design, so nobody can self-elevate
    // through registration. If this admin picked a different role or
    // status in the form, apply it now as a follow-up update using our
    // own admin session.
    const registeredUser = await registerUser({
      name: form.name,
      email: form.userId,
      password: DEFAULT_EMPLOYEE_PASSWORD,
    });

    let finalUser = registeredUser;
    if (registeredUser?.id && (form.role !== "user" || form.status !== "Active")) {
      finalUser = await updateUserRecord(registeredUser.id, {
        role: form.role,
        status: form.status,
      });
    }

    addEmployee({
      id: registeredUser?.id,
      name: finalUser?.name ?? form.name,
      userId: form.userId,
      role: finalUser?.role ?? "user",
      status: finalUser?.status ?? "Active",
      createdOn: finalUser?.createdOn,
    });
    setAlert({
      type: "success",
      message: `${form.name} was added successfully.`,
    });
    setModalOpen(false);
    setEditingEmployee(null);
    // Errors thrown by registerUser() propagate up to EmployeeFormModal,
    // which shows them inline and keeps the modal open for another attempt.
  };

  const handleDelete = (id) => {
    const employee = employees.find((emp) => emp.id === id);
    deleteEmployee(id);
    setAlert({
      type: "success",
      message: `${employee?.name ?? "Employee"} was marked inactive.`,
    });
  };

  const handleToggleStatus = (id) => {
    toggleStatus(id);
  };

  return (
    <section className="bg-white border border-slate-100 rounded-card p-5 sm:p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-btn bg-bgBlueTint flex items-center justify-center shrink-0">
            <Users className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Employee / User Management
            </h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Add and manage employee accounts, roles, and access status.
            </p>
          </div>
        </div>

        {canAddEmployee && (
          <button
            type="button"
            onClick={openAddModal}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors shrink-0"
          >
            <UserPlus className="w-4 h-4" />
            Add Employee
          </button>
        )}
      </div>

      {alert && (
        <InlineAlert
          type={alert.type}
          message={alert.message}
          onDismiss={() => setAlert(null)}
        />
      )}

      <EmployeeTable
        employees={visibleEmployees}
        onEdit={openEditModal}
        onDelete={handleDelete}
        onToggleStatus={handleToggleStatus}
      />

      <EmployeeFormModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingEmployee(null);
        }}
        onSubmit={handleSubmit}
        roleOptions={assignableRoleOptions}
        statusOptions={statusOptions}
        editingEmployee={editingEmployee}
        isUserIdTaken={isUserIdTaken}
      />
    </section>
  );
}
