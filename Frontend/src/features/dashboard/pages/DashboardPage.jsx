import { useAuth } from "../../auth/hooks/useAuth.js";

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-slate-900 mb-1">
        Welcome back, {user?.name?.split(" ")[0] ?? "there"} 👋
      </h1>
      <p className="text-slate-500 mb-8">
        Here's what's happening across your content pipeline today.
      </p>

      <div className="bg-white border border-slate-100 rounded-card p-6">
        <p className="text-sm text-slate-500">
          Dashboard widgets (recent activity, quick stats, shortcuts) will be
          built out in a later phase. For now, use the sidebar to explore the
          rest of the shell — Library, Learning Graph, Prompt Studio, ZIP
          Manager, Pipeline Monitor, Storage Explorer, Analytics, and Settings
          all route correctly.
        </p>
      </div>
    </div>
  );
}
