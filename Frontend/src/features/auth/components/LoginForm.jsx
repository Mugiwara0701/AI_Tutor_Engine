import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Mail, Lock, Eye, EyeOff, User } from "lucide-react";
import { useAuth } from "../hooks/useAuth.js";
import { cn } from "../../../utils/classNames.js";
import SocialAuthButtons from "./SocialAuthButtons.jsx";

export default function LoginForm({ mode = "login" }) {
  const isSignUp = mode === "signup";
  const { login, signUp, isLoading, error } = useAuth();
  const navigate = useNavigate();

  const [showPassword, setShowPassword] = useState(false);
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
      <div className="flex items-center justify-center gap-2 mb-6">
        <div className="relative w-9 h-9 rounded-lg bg-primary flex items-center justify-center">
          <span className="text-white font-bold text-base">M</span>
        </div>
        <span className="text-lg font-bold text-slate-900">AI Tutor</span>
      </div>

      <h2 className="text-[26px] font-bold text-slate-900 text-center mb-1.5">
        {isSignUp ? "Create an account" : "Welcome back"}
      </h2>
      <p className="text-sm text-slate-400 text-center mb-8">
        {isSignUp
          ? "Start your AI Tutor journey today."
          : "Sign in to continue your AI Tutor journey."}
      </p>

      {(formError || error) && (
        <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          {formError || error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {isSignUp && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Full name
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                required
                value={form.name}
                onChange={handleChange("name")}
                placeholder="Enter your full name"
                className="w-full pl-10 pr-3 py-3 rounded-lg border border-slate-200 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
            </div>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Email address
          </label>
          <div className="relative">
            <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="email"
              required
              value={form.email}
              onChange={handleChange("email")}
              placeholder="Enter your email"
              className="w-full pl-10 pr-3 py-3 rounded-lg border border-slate-200 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium text-slate-700">
              Password
            </label>
            {!isSignUp && (
              <Link
                to="#"
                className="text-sm font-medium text-primary hover:underline"
              >
                Forgot password?
              </Link>
            )}
          </div>
          <div className="relative">
            <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type={showPassword ? "text" : "password"}
              required
              value={form.password}
              onChange={handleChange("password")}
              placeholder="Enter your password"
              className="w-full pl-10 pr-10 py-3 rounded-lg border border-slate-200 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {!isSignUp && (
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="w-4 h-4 rounded border-slate-300 accent-primary focus:ring-primary/30"
            />
            <span className="text-sm text-slate-600">Remember me</span>
          </label>
        )}

        <button
          type="submit"
          disabled={isLoading}
          className={cn(
            "w-full py-3 rounded-lg bg-primary text-white text-[15px] font-semibold hover:bg-blue-700 transition-colors",
            isLoading && "opacity-70 cursor-not-allowed",
          )}
        >
          {isLoading ? "Please wait…" : isSignUp ? "Create account" : "Sign In"}
        </button>
      </form>

      {!isSignUp && (
        <>
          <div className="flex items-center gap-3 my-6">
            <div className="flex-1 h-px bg-slate-200" />
            <span className="text-xs text-slate-400">or</span>
            <div className="flex-1 h-px bg-slate-200" />
          </div>
          <SocialAuthButtons />
        </>
      )}

      <p className="text-center text-sm text-slate-500 mt-6">
        {isSignUp ? (
          <>
            Already have an account?{" "}
            <Link
              to="/login"
              className="text-primary font-medium hover:underline"
            >
              Sign in
            </Link>
          </>
        ) : (
          <>
            Don&apos;t have an account?{" "}
            <Link
              to="/signup"
              className="text-primary font-medium hover:underline"
            >
              Create an account
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
