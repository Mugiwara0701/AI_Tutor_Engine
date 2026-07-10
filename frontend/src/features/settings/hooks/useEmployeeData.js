// src/features/settings/hooks/useEmployeeData.js
//
// Employee / user management state, backed by the real backend
// (/auth/users routes). Loads on mount and keeps local state in sync
// with each create/update/delete call.

import { useCallback, useEffect, useState } from "react";
import {
  fetchUsers,
  updateUserRecord,
  deleteUserRecord,
} from "../api/employeeApi.js";

const ROLE_OPTIONS = ["Admin", "Editor", "Viewer", "Employee", "user"];
const STATUS_OPTIONS = ["Active", "Inactive"];

export function useEmployeeData() {
  const [employees, setEmployees] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadEmployees = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const users = await fetchUsers();
      setEmployees(users);
    } catch (err) {
      setError(err.message || "Failed to load employees.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadEmployees();
  }, [loadEmployees]);

  // Called right after a successful /auth/register call (done by the
  // caller) — just adds the already-created user into local state instead
  // of registering it again.
  const addEmployee = (employee) => {
    setEmployees((prev) => [employee, ...prev]);
  };

  const updateEmployee = async (id, updates) => {
    const updated = await updateUserRecord(id, updates);
    setEmployees((prev) =>
      prev.map((emp) => (emp.id === id ? { ...emp, ...updated } : emp)),
    );
    return updated;
  };

  const deleteEmployee = async (id) => {
    await deleteUserRecord(id);
    setEmployees((prev) => prev.filter((emp) => emp.id !== id));
  };

  const toggleStatus = async (id) => {
    const target = employees.find((emp) => emp.id === id);
    if (!target) return;
    await updateEmployee(id, {
      status: target.status === "Active" ? "Inactive" : "Active",
    });
  };

  const isUserIdTaken = (userId, excludeId) =>
    employees.some(
      (emp) =>
        emp.id !== excludeId &&
        emp.userId.toLowerCase() === userId.trim().toLowerCase(),
    );

  return {
    employees,
    isLoading,
    error,
    roleOptions: ROLE_OPTIONS,
    statusOptions: STATUS_OPTIONS,
    addEmployee,
    updateEmployee,
    deleteEmployee,
    toggleStatus,
    isUserIdTaken,
    refresh: loadEmployees,
  };
}
