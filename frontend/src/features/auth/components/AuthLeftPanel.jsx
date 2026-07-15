// src/features/auth/components/AuthLeftPanel.jsx
//
// Branding/preview panel for the auth screens. Text outside the white
// Learning Graph card uses light colors to stay readable on the dark
// gradient page background.

import { Sparkles, ShieldCheck } from "lucide-react";

export default function AuthLeftPanel() {
  return (
    <div className="hidden lg:block max-w-[520px]">
      <div className="flex items-center gap-2.5 mb-8">
        <div className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-base">M</span>
        </div>
        <span className="text-lg font-semibold tracking-tight text-white">
          AI Tutor
        </span>
      </div>

      <h1 className="text-[38px] leading-[1.2] font-bold tracking-tight text-white mb-4">
        AI-powered learning made{" "}
        <span className="text-sky-400">effortless.</span>
      </h1>
      <p className="text-slate-300 text-[15px] leading-relaxed mb-8 max-w-[480px]">
        Create, organize, and manage educational content with the power of AI.
      </p>

      {/* Learning Graph preview — stays white/dark-text, unchanged */}
      <div className="bg-white rounded-card border border-slate-200 shadow-card p-5 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-6 h-6 rounded-md bg-primary flex items-center justify-center">
            <span className="text-white text-[11px] font-bold">M</span>
          </div>
          <span className="text-slate-700 text-sm font-semibold">
            Learning Graph
          </span>
        </div>

        <div className="relative h-44">
          <svg
            className="absolute inset-0 w-full h-full"
            viewBox="0 0 460 180"
            fill="none"
            aria-hidden="true"
          >
            <line
              x1="230"
              y1="90"
              x2="230"
              y2="28"
              stroke="#cbd5e1"
              strokeDasharray="3 3"
            />
            <line
              x1="230"
              y1="90"
              x2="105"
              y2="58"
              stroke="#cbd5e1"
              strokeDasharray="3 3"
            />
            <line
              x1="230"
              y1="90"
              x2="355"
              y2="58"
              stroke="#cbd5e1"
              strokeDasharray="3 3"
            />
            <line
              x1="230"
              y1="90"
              x2="105"
              y2="128"
              stroke="#cbd5e1"
              strokeDasharray="3 3"
            />
            <line
              x1="230"
              y1="90"
              x2="355"
              y2="128"
              stroke="#cbd5e1"
              strokeDasharray="3 3"
            />
            <line
              x1="230"
              y1="90"
              x2="230"
              y2="158"
              stroke="#cbd5e1"
              strokeDasharray="3 3"
            />
          </svg>

          <div className="absolute left-1/2 top-0 -translate-x-1/2 bg-sky-50 border border-sky-100 rounded-lg px-3 py-1.5 text-center">
            <p className="text-[11px] font-semibold text-slate-700">
              Lesson Plan
            </p>
            <p className="text-[10px] text-slate-400">AI Generated</p>
          </div>
          <div className="absolute left-0 top-[26%] bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
            <p className="text-[11px] font-semibold text-slate-700">
              Learning Objectives
            </p>
          </div>
          <div className="absolute right-0 top-[26%] bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-1.5 text-center">
            <p className="text-[11px] font-semibold text-slate-700">
              Assessment
            </p>
            <p className="text-[10px] text-slate-400">Auto-Generated</p>
          </div>
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-primary rounded-lg px-4 py-2 shadow-sm">
            <p className="text-xs font-semibold text-white whitespace-nowrap">
              Course Overview
            </p>
          </div>
          <div className="absolute left-0 bottom-[6%] bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
            <p className="text-[11px] font-semibold text-slate-700">
              Study Materials
            </p>
            <p className="text-[10px] text-slate-400">Curated</p>
          </div>
          <div className="absolute right-0 bottom-[6%] bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-1.5 text-center">
            <p className="text-[11px] font-semibold text-slate-700">
              Student Progress
            </p>
            <p className="text-[10px] text-slate-400">Tracked</p>
          </div>
          <div className="absolute left-1/2 bottom-0 -translate-x-1/2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5">
            <p className="text-[11px] font-semibold text-slate-700">
              Content Outline
            </p>
          </div>
        </div>
      </div>

      {/* Feature highlights — light text for dark background */}
      <div className="flex items-start gap-8">
        <div className="flex items-start gap-2.5">
          <div className="w-8 h-8 rounded-md bg-white/10 flex items-center justify-center shrink-0">
            <Sparkles className="w-4 h-4 text-sky-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">AI Powered</p>
            <p className="text-xs text-slate-400">Smart content generation</p>
          </div>
        </div>
        <div className="flex items-start gap-2.5">
          <div className="w-8 h-8 rounded-md bg-white/10 flex items-center justify-center shrink-0">
            <ShieldCheck className="w-4 h-4 text-sky-400" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">Secure & Private</p>
            <p className="text-xs text-slate-400">Your data stays protected</p>
          </div>
        </div>
      </div>
    </div>
  );
}
