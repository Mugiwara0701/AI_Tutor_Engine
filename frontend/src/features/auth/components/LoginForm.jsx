import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Mail, User } from "lucide-react";
import { useAuth } from "../hooks/useAuth.js";
import FormInput from "../../../components/ui/FormInput.jsx";
import PasswordInput from "../../../components/ui/PasswordInput.jsx";
import PrimaryButton from "../../../components/ui/PrimaryButton.jsx";
import SocialAuthButtons from "./SocialAuthButtons.jsx";

export default function LoginForm({ mode = "login" }) {
  const isSignUp = mode === "signup";
  const { login, signUp, isLoading, error } = useAuth();
  const navigate = useNavigate();

  const [rememberMe, setRememberMe] = useState(true);
  const [formError, setFormError] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", password: "" });

  const handleChange = (field) => (e) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);
    try {
      if (isSignUp) {
        await signUp(form);
      } else {
        await login({ email: form.email, password: form.password });
      }
      navigate("/dashboard");
    } catch (err) {
      setFormError(err.message || "Something went wrong.");
    }
  };

  return (
    <div>
      <div className="flex flex-col items-center text-center mb-7 ">
        <h2 className="text-[24px] font-bold text-slate-900 mb-1.5">
          {isSignUp ? "Create an account" : "Welcome back"}
        </h2>
        <p className="text-sm text-slate-500">
          Sign in to continue to your workspace
        </p>
      </div>

      {(formError || error) && (
        <div
          role="alert"
          className="mb-5 text-sm text-red-700 bg-red-50 border border-red-100 rounded-lg px-3.5 py-2.5"
        >
          {formError || error}
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
        {isSignUp && (
          <FormInput
            id="auth-name"
            label="Full name"
            icon={User}
            type="text"
            autoComplete="name"
            required
            value={form.name}
            onChange={handleChange("name")}
            placeholder="Enter your full name"
          />
        )}

        <FormInput
          id="auth-email"
          label="Email address"
          icon={Mail}
          type="email"
          autoComplete="email"
          required
          value={form.email}
          onChange={handleChange("email")}
          placeholder="Enter your email"
        />

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label
              htmlFor="auth-password"
              className="text-sm font-medium text-slate-700"
            >
              Password
            </label>
            {!isSignUp && (
              <Link
                to="#"
                className="text-sm font-medium text-primary hover:text-primaryHover hover:underline"
              >
                Forgot password?
              </Link>
            )}
          </div>
          <PasswordInput
            id="auth-password"
            label={null}
            autoComplete={isSignUp ? "new-password" : "current-password"}
            required
            value={form.password}
            onChange={handleChange("password")}
            placeholder="Enter your password"
          />
        </div>

        {!isSignUp && (
          <label className="flex items-center gap-2.5 cursor-pointer select-none -mt-1">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 accent-primary focus:ring-2 focus:ring-primary/30"
            />
            <span className="text-sm text-slate-600">Remember me</span>
          </label>
        )}

        <PrimaryButton
          type="submit"
          isLoading={isLoading}
          loadingText="Please wait…"
          className="w-full mt-1"
        >
          {isSignUp ? "Create account" : "Sign in"}
        </PrimaryButton>
      </form>
    </div>
  );
}
