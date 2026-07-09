// src/features/auth/pages/SignUpPage.jsx
// Placeholder for SignUpPage — implement component/logic here.
import AuthLayout from "../../../layouts/AuthLayout.jsx";
import LoginForm from "../components/LoginForm.jsx";

export default function SignUpPage() {
  return (
    <AuthLayout>
      <LoginForm mode="signup" />
    </AuthLayout>
  );
}
