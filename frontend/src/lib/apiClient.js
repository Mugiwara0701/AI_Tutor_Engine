// src/lib/apiClient.js
//
// Thin fetch wrapper for the dashboard backend. All backend responses are
// shaped like: { success: bool, message: string, data: any }
// This wrapper unwraps that envelope and throws a plain Error with the
// backend's message on failure, so calling code can just try/catch.

import { API_BASE_URL, AUTH_TOKEN_STORAGE_KEY } from "./constants.js";

export function getStoredToken() {
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function setStoredToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  }
}

/**
 * @param {string} path - e.g. "/auth/login"
 * @param {object} [options]
 * @param {string} [options.method="GET"]
 * @param {object} [options.body] - will be JSON.stringified
 * @param {boolean} [options.auth=false] - attach Authorization: Bearer <token>
 */
export async function apiRequest(
  path,
  { method = "GET", body, auth = false } = {},
) {
  const headers = { "Content-Type": "application/json" };

  if (auth) {
    const token = getStoredToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (networkErr) {
    throw new Error(
      `Could not reach the backend at ${API_BASE_URL}. Is it running? (${networkErr.message})`,
    );
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // No JSON body (e.g. some 500s) — fall through with payload=null
  }

  if (!response.ok || (payload && payload.success === false)) {
    const message =
      payload?.message || `Request failed with status ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.data = payload?.data;
    throw error;
  }

  return payload?.data;
}
