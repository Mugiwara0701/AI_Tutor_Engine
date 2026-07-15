// src/components/ui/FormInput.jsx
//
// Shared labeled input for forms. Visual-only primitive: always renders a
// real <label>, a fixed comfortable height, and a consistent focus ring so
// every form in the app (starting with Login/Signup) looks and behaves the
// same way. Wraps a plain <input> — all native props pass through.

import { forwardRef } from "react";
import { cn } from "../../utils/classNames.js";

const FormInput = forwardRef(function FormInput(
  {
    id,
    label,
    icon: Icon,
    error,
    trailing,
    className,
    inputClassName,
    ...inputProps
  },
  ref,
) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {label && (
        <label
          htmlFor={id}
          className="text-sm font-medium text-slate-700"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {Icon && (
          <Icon
            className="w-4.5 h-4.5 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none"
            aria-hidden="true"
          />
        )}
        <input
          id={id}
          ref={ref}
          aria-invalid={error ? "true" : undefined}
          className={cn(
            "w-full h-12 rounded-lg border bg-white text-[15px] text-slate-900 placeholder:text-slate-400 transition-colors",
            "focus:outline-none focus:ring-4 focus:ring-primary/10 focus:border-primary",
            Icon ? "pl-10" : "pl-3.5",
            trailing ? "pr-11" : "pr-3.5",
            error
              ? "border-red-300 focus:border-red-400 focus:ring-red-100"
              : "border-slate-200 hover:border-slate-300",
            inputClassName,
          )}
          {...inputProps}
        />
        {trailing && (
          <div className="absolute right-3.5 top-1/2 -translate-y-1/2">
            {trailing}
          </div>
        )}
      </div>
      {error && (
        <p className="text-xs font-medium text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
});

export default FormInput;
