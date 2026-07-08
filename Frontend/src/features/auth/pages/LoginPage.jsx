// src/features/auth/pages/LoginPage.jsx
// Placeholder for LoginPage — implement component/logic here.

import AuthLayout from "../../../layouts/AuthLayout.jsx";
import LoginForm from "../components/LoginForm.jsx";

export default function LoginPage() {
  return (
    <AuthLayout>
      <LoginForm mode="login" />
    </AuthLayout>
  );
}
