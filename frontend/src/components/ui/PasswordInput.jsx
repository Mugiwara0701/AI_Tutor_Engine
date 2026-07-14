// src/components/ui/PasswordInput.jsx
//
// Password field with a show/hide toggle. Same visual language as
// FormInput (they share the same input chrome), with an accessible
// icon-button for visibility instead of a generic trailing icon.

import { forwardRef, useState } from "react";
import { Lock, Eye, EyeOff } from "lucide-react";
import FormInput from "./FormInput.jsx";

const PasswordInput = forwardRef(function PasswordInput(
  { id, label = "Password", ...props },
  ref,
) {
  const [visible, setVisible] = useState(false);

  return (
    <FormInput
      id={id}
      ref={ref}
      label={label}
      icon={Lock}
      type={visible ? "text" : "password"}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="p-1 -m-1 text-slate-400 hover:text-slate-600 transition-colors rounded focus:outline-none focus:ring-2 focus:ring-primary/30"
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          tabIndex={0}
        >
          {visible ? (
            <EyeOff className="w-4.5 h-4.5" aria-hidden="true" />
          ) : (
            <Eye className="w-4.5 h-4.5" aria-hidden="true" />
          )}
        </button>
      }
      {...props}
    />
  );
});

export default PasswordInput;
