export default function FeatureBadge({ icon: Icon, title, subtitle }) {
  return (
    <div className="flex items-center gap-2.5 max-w-[190px]">
      <div className="w-9 h-9 rounded-lg bg-indigo-50 flex items-center justify-center shrink-0">
        <Icon className="w-4 h-4 text-primary" />
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-800 leading-tight">
          {title}
        </p>
        <p className="text-xs text-slate-400 leading-snug">{subtitle}</p>
      </div>
    </div>
  );
}
