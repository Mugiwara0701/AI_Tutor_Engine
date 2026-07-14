import AuthLeftPanel from "../features/auth/components/AuthLeftPanel.jsx";
import AuthBackgroundArt from "../features/auth/components/AuthBackgroundArt.jsx";

export default function AuthLayout({ children }) {
  return (
    <div className="login-background relative min-h-screen w-full overflow-hidden">
      {/* Flowing network illustration, bottom-left — unchanged from before */}
      <AuthBackgroundArt />

      <div className="relative min-h-screen flex items-center justify-center px-6 py-12 lg:px-16">
        <div className="w-full max-w-[1200px] flex flex-col lg:flex-row items-center gap-12 lg:gap-20">
          <div className="w-full lg:flex-1">
            <AuthLeftPanel />
          </div>

          <div className="w-full lg:w-[440px] lg:shrink-0">
            <div className="bg-white rounded-card border border-white/10 shadow-card-lg px-7 py-9 sm:px-10 sm:py-10">
              {children}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
