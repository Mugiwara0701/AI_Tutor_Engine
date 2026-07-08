// src/components/ui/SearchBar.jsx
// Placeholder for SearchBar — implement component/logic here.

// src/components/ui/SearchBar.jsx

import { Search } from "lucide-react";
import { cn } from "../../utils/classNames.js";

/**
 * Search input with an optional keyboard shortcut hint (e.g. "⌘K") shown
 * on the right when the field is empty.
 */
export default function SearchBar({
  value,
  onChange,
  placeholder = "Search…",
  shortcutHint,
  className,
  inputRef,
}) {
  return (
    <div className={cn("relative", className)}>
      <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-9 pr-16 py-2 rounded-btn border border-slate-200 bg-white text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 transition-colors"
      />
      {shortcutHint && !value && (
        <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 px-1.5 py-0.5 rounded border border-slate-200 bg-slate-50 text-[10px] font-medium text-slate-400">
          {shortcutHint}
        </kbd>
      )}
    </div>
  );
}
