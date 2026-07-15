// src/components/ui/PrimaryButton.jsx
//
// Base of the shared button hierarchy (primary / outline / ghost).
// Starts here with "primary" since that's what Login/Signup need;
// variants below exist so the same component can be reused once the
// rest of the app is brought onto the design system.

import { Loader2 } from "lucide-react";
import { cn } from "../../utils/classNames.js";

const VARIANTS = {
  primary:
    "bg-primary text-white hover:bg-primaryHover shadow-sm shadow-primary/20",
  outline:
    "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50",
  ghost: "bg-transparent text-slate-600 hover:bg-slate-50",
  destructive: "bg-red-600 text-white hover:bg-red-700",
};

export default function PrimaryButton({
  children,
  variant = "primary",
  isLoading = false,
  loadingText,
  className,
  disabled,
  type = "button",
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || isLoading}
      className={cn(
        "inline-flex items-center justify-center gap-2 h-12 px-5 rounded-lg text-[15px] font-semibold transition-colors",
        "focus:outline-none focus:ring-4 focus:ring-primary/15",
        "disabled:opacity-60 disabled:cursor-not-allowed",
        VARIANTS[variant] ?? VARIANTS.primary,
        className,
      )}
      {...props}
    >
      {isLoading && (
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
      )}
      {isLoading && loadingText ? loadingText : children}
    </button>
  );
}
