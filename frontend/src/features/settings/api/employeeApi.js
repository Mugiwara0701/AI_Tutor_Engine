// src/features/settings/api/employeeApi.js
//
// Real backend calls for employee/user management. Talks to the FastAPI
// dashboard backend's /auth/users routes. Maps backend field names
// (full_name, is_active) to the shape the Settings UI already expects
// (name, status).

import { apiRequest } from "../../../lib/apiClient.js";

function mapUser(user) {
  if (!user) return null;
  return {
    id: user.id,
    name: user.full_name,
    userId: user.email,
    role: user.role,
    status: user.is_active ? "Active" : "Inactive",
    createdOn: user.created_at,
  };
}

/**
 * Fetches all employees/users, including inactive (soft-deleted /
 * deactivated) ones, so the Settings table can still show them with an
 * "Inactive" status badge instead of hiding them entirely.
 */
export async function fetchUsers() {
  const data = await apiRequest("/auth/users?include_inactive=true", {
    auth: true,
  });
  return (data ?? []).map(mapUser);
}

/**
 * Updates a user's name, role, and/or active status.
 * Email and password are not editable through this endpoint.
 */
export async function updateUserRecord(id, { name, role, status } = {}) {
  const body = {};
  if (name !== undefined) body.full_name = name;
  if (role !== undefined) body.role = role;
  if (status !== undefined) body.is_active = status === "Active";

  const data = await apiRequest(`/auth/users/${id}`, {
    method: "PATCH",
    body,
    auth: true,
  });
  return mapUser(data);
}

/**
 * Soft-deletes a user. The backend sets is_active=false rather than
 * permanently removing the record, so the row remains in the database
 * and simply drops out of the normal (active-only) employee list.
 */
export async function deleteUserRecord(id) {
  await apiRequest(`/auth/users/${id}`, { method: "DELETE", auth: true });
}
