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
import { DEFAULT_EMPLOYEE_PASSWORD } from "../../../lib/constants.js";

export default function EmployeeManagementSection() {
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
      updateEmployee(editingEmployee.id, form);
      setAlert({
        type: "success",
        message: `${form.name}'s details were updated.`,
      });
      setModalOpen(false);
      setEditingEmployee(null);
      return;
    }

    // Register the new employee against the real backend, using the same
    // fixed default password for every account created here.
    const registeredUser = await registerUser({
      name: form.name,
      email: form.userId,
      password: DEFAULT_EMPLOYEE_PASSWORD,
    });

    addEmployee({
      name: registeredUser?.name ?? form.name,
      userId: form.userId,
      role: form.role,
      status: form.status,
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
      message: `${employee?.name ?? "Employee"} was removed.`,
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

        <button
          type="button"
          onClick={openAddModal}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors shrink-0"
        >
          <UserPlus className="w-4 h-4" />
          Add Employee
        </button>
      </div>

      {alert && (
        <InlineAlert
          type={alert.type}
          message={alert.message}
          onDismiss={() => setAlert(null)}
        />
      )}

      <EmployeeTable
        employees={employees}
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
        roleOptions={roleOptions}
        statusOptions={statusOptions}
        editingEmployee={editingEmployee}
        isUserIdTaken={isUserIdTaken}
      />
    </section>
  );
}
