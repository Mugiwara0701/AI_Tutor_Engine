// src/lib/constants.js
// Placeholder for constants — implement component/logic here.

// src/lib/constants.js

// Base URL of the FastAPI dashboard backend.
// Override by creating a `.env` file with VITE_API_BASE_URL=http://localhost:8000
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

// localStorage key used to persist the JWT between page reloads.
export const AUTH_TOKEN_STORAGE_KEY = "ai_tutor_access_token";
