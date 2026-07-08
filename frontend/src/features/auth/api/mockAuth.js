// src/features/auth/api/mockAuth.js
// Placeholder for mockAuth — implement component/logic here.

// Simulated auth API — swap these for real fetch calls once the backend exists.

const FAKE_LATENCY_MS = 700;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function mockLogin({ email, password }) {
  await delay(FAKE_LATENCY_MS);

  if (!email || !password) {
    throw new Error("Email and password are required.");
  }

  return {
    id: "user_1",
    name: "Mohit Mali",
    email,
    role: "Content Admin",
    avatarUrl: null,
  };
}

export async function mockSignUp({ name, email, password }) {
  await delay(FAKE_LATENCY_MS);

  if (!name || !email || !password) {
    throw new Error("Name, email, and password are required.");
  }

  return {
    id: "user_new",
    name,
    email,
    role: "Content Developer",
    avatarUrl: null,
  };
}

export async function mockSocialLogin(provider) {
  await delay(FAKE_LATENCY_MS);
  return {
    id: "user_social",
    name: "Mohit Mali",
    email: `mohit@${provider.toLowerCase()}.com`,
    role: "Content Admin",
    avatarUrl: null,
  };
}
