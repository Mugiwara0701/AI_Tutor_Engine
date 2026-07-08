import AuthLeftPanel from "../features/auth/components/AuthLeftPanel.jsx";

export default function AuthLayout({ children }) {
  return (
    <div className="min-h-screen w-full bg-bgBlueTint flex items-center justify-center p-4 sm:p-8">
      <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-16 items-center">
        <AuthLeftPanel />
        <div className="flex items-center justify-center">
          <div className="w-full max-w-[500px] bg-white rounded-3xl shadow-xl shadow-slate-200/60 border border-slate-100 p-8 sm:p-12">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
