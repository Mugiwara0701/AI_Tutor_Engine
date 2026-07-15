// src/features/auth/api/authApi.js
//
// Real backend calls for authentication. Talks to the FastAPI dashboard
// backend's /auth/* routes. Maps backend field names (full_name, avatar_url)
// to the shape the rest of the frontend already expects (name, avatarUrl).

import { apiRequest, setStoredToken } from "../../../lib/apiClient.js";

function mapProfile(profile) {
  if (!profile) return null;
  return {
    id: profile.id,
    name: profile.full_name,
    email: profile.email,
    role: profile.role,
    avatarUrl: profile.avatar_url,
    isActive: profile.is_active,
  };
}

/**
 * Registers a new account. The backend does not return a token on
 * register (no Supabase Auth session), so callers should immediately
 * follow this with loginUser() using the same credentials.
 */
export async function registerUser({ name, email, password }) {
  const data = await apiRequest("/auth/register", {
    method: "POST",
    body: { email, password, full_name: name },
  });
  return mapProfile(data.user);
}

/**
 * Logs in, stores the JWT in localStorage, and returns the mapped user.
 */
export async function loginUser({ email, password }) {
  const data = await apiRequest("/auth/login", {
    method: "POST",
    body: { email, password },
  });

  const token = data?.session?.access_token;
  if (!token) {
    throw new Error("Login succeeded but no access token was returned.");
  }

  setStoredToken(token);
  return mapProfile(data.user);
}

/**
 * Combined register + login, since the backend issues no token on register.
 * This is what the sign-up form should call.
 */
export async function signUpUser({ name, email, password }) {
  await registerUser({ name, email, password });
  return loginUser({ email, password });
}

/**
 * Fetches the current user using whatever token is stored. Used on app
 * load to restore a session after a page refresh.
 */
export async function fetchCurrentUser() {
  const data = await apiRequest("/auth/me", { auth: true });
  return mapProfile(data);
}

/**
 * Changes the current user's own password. Requires the current password
 * for verification. On success the backend revokes all of this user's
 * sessions (including the one making this call), so the caller should
 * clear the stored token and send them back to login.
 */
export async function changePassword({ currentPassword, newPassword }) {
  await apiRequest("/auth/change-password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
    auth: true,
  });
}

/**
 * Best-effort logout call to the backend (ends the session record server
 * side). Callers should clear local token/state regardless of whether
 * this succeeds.
 */
export async function logoutUser() {
  await apiRequest("/auth/logout", { method: "POST", auth: true });
}
