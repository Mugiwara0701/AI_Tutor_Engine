import { useState } from "react";
import { mockSocialLogin } from "../api/mockAuth.js";
import { useAuth } from "../hooks/useAuth.js";
import { useNavigate } from "react-router-dom";

function GoogleIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.99.66-2.25 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.43.34-2.09V7.07H2.18A11 11 0 0 0 1 12c0 1.77.42 3.45 1.18 4.93z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15A10.98 10.98 0 0 0 12 1a11 11 0 0 0-9.82 6.07L5.84 9.9C6.71 7.31 9.14 5.38 12 5.38z"
      />
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24">
      <rect x="2" y="2" width="9" height="9" fill="#F25022" />
      <rect x="13" y="2" width="9" height="9" fill="#7FBA00" />
      <rect x="2" y="13" width="9" height="9" fill="#00A4EF" />
      <rect x="13" y="13" width="9" height="9" fill="#FFB900" />
    </svg>
  );
}

export default function SocialAuthButtons() {
  const [loadingProvider, setLoadingProvider] = useState(null);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSocialLogin = async (provider) => {
    setLoadingProvider(provider);
    try {
      const user = await mockSocialLogin(provider);
      await login({ email: user.email, password: "social-oauth-token" });
      navigate("/dashboard");
    } catch {
      // no-op: mock provider, real error handling comes with real OAuth
    } finally {
      setLoadingProvider(null);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-3">
      <button
        type="button"
        onClick={() => handleSocialLogin("Google")}
        disabled={loadingProvider !== null}
        className="flex items-center justify-center gap-2 h-12 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-colors disabled:opacity-60 focus:outline-none focus:ring-4 focus:ring-primary/10"
      >
        <GoogleIcon />
        {loadingProvider === "Google" ? "Signing in…" : "Google"}
      </button>
      <button
        type="button"
        onClick={() => handleSocialLogin("Microsoft")}
        disabled={loadingProvider !== null}
        className="flex items-center justify-center gap-2 h-12 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-colors disabled:opacity-60 focus:outline-none focus:ring-4 focus:ring-primary/10"
      >
        <MicrosoftIcon />
        {loadingProvider === "Microsoft" ? "Signing in…" : "Microsoft"}
      </button>
    </div>
  );
}
