// src/features/settings/components/EmployeeFormModal.jsx
//
// Frontend-only form UI. Validates locally and hands the result back to the
// parent via onSubmit — no network calls, no persistence.

import { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import { cn } from "../../../utils/classNames.js";

const EMPTY_FORM = {
  name: "",
  userId: "",
  password: "",
  role: "",
  status: "Active",
};

function validate(form, { isUserIdTaken }) {
  const errors = {};
  if (!form.name.trim()) errors.name = "Employee name is required.";
  if (!form.userId.trim()) {
    errors.userId = "User ID / Username is required.";
  } else if (isUserIdTaken(form.userId)) {
    errors.userId = "This User ID is already taken.";
  }
  if (!form.password.trim()) errors.password = "Password is required.";
  if (!form.role) errors.role = "Role is required.";
  if (!form.status) errors.status = "Status is required.";
  return errors;
}

export default function EmployeeFormModal({
  open,
  onClose,
  onSubmit,
  roleOptions,
  statusOptions,
  editingEmployee,
  isUserIdTaken,
}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [showPassword, setShowPassword] = useState(false);

  const isEditing = Boolean(editingEmployee);

  useEffect(() => {
    if (!open) return;
    setForm(
      editingEmployee
        ? {
            name: editingEmployee.name,
            userId: editingEmployee.userId,
            password: editingEmployee.password,
            role: editingEmployee.role,
            status: editingEmployee.status,
          }
        : EMPTY_FORM,
    );
    setErrors({});
    setShowPassword(false);
  }, [open, editingEmployee]);

  const setField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  const handleReset = () => {
    setForm(isEditing ? { ...editingEmployee } : EMPTY_FORM);
    setErrors({});
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const nextErrors = validate(form, {
      isUserIdTaken: (userId) =>
        isUserIdTaken(userId, isEditing ? editingEmployee.id : undefined),
    });
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    onSubmit(form);
  };

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title={isEditing ? "Edit Employee" : "Add Employee"}
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Employee Name
          </label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setField("name", e.target.value)}
            placeholder="e.g. Priya Sharma"
            className={cn(
              "w-full px-3 py-2 rounded-btn border bg-white text-sm text-slate-700 placeholder:text-slate-400 transition-colors",
              "focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40",
              errors.name ? "border-red-300" : "border-slate-200",
            )}
          />
          {errors.name && (
            <p className="text-xs text-red-600 mt-1">{errors.name}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            User ID / Username
          </label>
          <input
            type="text"
            value={form.userId}
            onChange={(e) => setField("userId", e.target.value)}
            placeholder="e.g. priya.sharma"
            className={cn(
              "w-full px-3 py-2 rounded-btn border bg-white text-sm text-slate-700 placeholder:text-slate-400 transition-colors",
              "focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40",
              errors.userId ? "border-red-300" : "border-slate-200",
            )}
          />
          {errors.userId && (
            <p className="text-xs text-red-600 mt-1">{errors.userId}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            Password
          </label>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={form.password}
              onChange={(e) => setField("password", e.target.value)}
              placeholder="Enter a password"
              className={cn(
                "w-full pl-3 pr-10 py-2 rounded-btn border bg-white text-sm text-slate-700 placeholder:text-slate-400 transition-colors",
                "focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40",
                errors.password ? "border-red-300" : "border-slate-200",
              )}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded text-slate-400 hover:text-slate-600 transition-colors"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
          {errors.password && (
            <p className="text-xs text-red-600 mt-1">{errors.password}</p>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Role
            </label>
            <Dropdown
              value={form.role}
              onChange={(v) => setField("role", v)}
              options={roleOptions}
              placeholder="Select role"
              className={cn(errors.role && "[&_select]:border-red-300")}
            />
            {errors.role && (
              <p className="text-xs text-red-600 mt-1">{errors.role}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              Status
            </label>
            <div className="flex items-center gap-1 p-1 bg-slate-50 rounded-btn border border-slate-200">
              {statusOptions.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setField("status", option)}
                  className={cn(
                    "flex-1 px-3 py-1.5 rounded-[6px] text-sm font-medium transition-colors",
                    form.status === option
                      ? option === "Active"
                        ? "bg-white text-green-600 shadow-sm"
                        : "bg-white text-slate-500 shadow-sm"
                      : "text-slate-400 hover:text-slate-600",
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
            {errors.status && (
              <p className="text-xs text-red-600 mt-1">{errors.status}</p>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={handleReset}
            className="px-3.5 py-2 rounded-btn border border-slate-200 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
          >
            Reset
          </button>
          <button
            type="submit"
            className="px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            {isEditing ? "Save Changes" : "Add Employee"}
          </button>
        </div>
      </form>
    </ModalDialog>
  );
}
