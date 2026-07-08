// src/features/settings/hooks/useEmployeeData.js
//
// Frontend-only employee/user management state.
// Everything lives in React state — nothing is persisted or sent to a backend.

import { useState } from "react";
import mockEmployees from "../data/mockEmployees.json";

let idCounter = mockEmployees.employees.length + 1;

function generateId() {
  return `emp-${idCounter++}`;
}

export function useEmployeeData() {
  const [employees, setEmployees] = useState(mockEmployees.employees);

  const addEmployee = (employee) => {
    const newEmployee = {
      id: generateId(),
      createdOn: new Date().toISOString(),
      ...employee,
    };
    setEmployees((prev) => [newEmployee, ...prev]);
    return newEmployee;
  };

  const updateEmployee = (id, updates) => {
    setEmployees((prev) =>
      prev.map((emp) => (emp.id === id ? { ...emp, ...updates } : emp)),
    );
  };

  const deleteEmployee = (id) => {
    setEmployees((prev) => prev.filter((emp) => emp.id !== id));
  };

  const toggleStatus = (id) => {
    setEmployees((prev) =>
      prev.map((emp) =>
        emp.id === id
          ? { ...emp, status: emp.status === "Active" ? "Inactive" : "Active" }
          : emp,
      ),
    );
  };

  const isUserIdTaken = (userId, excludeId) =>
    employees.some(
      (emp) =>
        emp.id !== excludeId &&
        emp.userId.toLowerCase() === userId.trim().toLowerCase(),
    );

  return {
    employees,
    roleOptions: mockEmployees.roleOptions,
    statusOptions: mockEmployees.statusOptions,
    addEmployee,
    updateEmployee,
    deleteEmployee,
    toggleStatus,
    isUserIdTaken,
  };
}
