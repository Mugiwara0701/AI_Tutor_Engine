import { Sparkles, ShieldCheck } from "lucide-react";
import LearningGraphPreview from "./LearningGraphPreview.jsx";
import FeatureBadge from "./FeatureBadge.jsx";

export default function AuthLeftPanel() {
  return (
    <div className="hidden lg:flex flex-col justify-center px-2">
      <div className="flex items-center gap-2.5 mb-9">
        <div className="relative w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
          <span className="text-white font-bold text-lg">M</span>
          <Sparkles className="w-4 h-4 text-yellow-300 fill-yellow-300 absolute -top-1.5 -right-1.5" />
        </div>
        <span className="text-xl font-bold text-slate-900">AI Tutor</span>
      </div>

      <h1 className="text-[40px] font-bold text-slate-900 leading-[1.15] mb-4">
        AI-powered learning made{" "}
        <span className="text-primary">effortless.</span>
      </h1>

      <p className="text-slate-500 text-base mb-9 max-w-sm">
        Create, organize, and manage educational content with the power of AI.
      </p>

      <LearningGraphPreview />

      <div className="flex items-center gap-6 mt-9">
        <FeatureBadge
          icon={Sparkles}
          title="AI Powered"
          subtitle="Smart content generation and insights"
        />
        <FeatureBadge
          icon={ShieldCheck}
          title="Secure & Private"
          subtitle="Your data stays safe and protected"
        />
      </div>
    </div>
  );
}
