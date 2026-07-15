// src/features/settings/components/ChangePasswordSection.jsx
//
// Lets the logged-in user change their own password (dashboard flow, not
// "forgot password" — requires knowing the current password). Calls the
// real backend via changePassword() in authApi.js.

import { useState } from "react";
import { KeyRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import PasswordInput from "../../../components/ui/PasswordInput.jsx";
import InlineAlert from "../../../components/shared/InlineAlert.jsx";
import { changePassword } from "../../auth/api/authApi.js";
import { useAuth } from "../../auth/hooks/useAuth.js";

const EMPTY_FORM = { currentPassword: "", newPassword: "", confirmPassword: "" };

function validate(form) {
  const errors = {};
  if (!form.currentPassword) {
    errors.currentPassword = "Enter your current password.";
  }
  if (!form.newPassword) {
    errors.newPassword = "Enter a new password.";
  } else if (form.newPassword.length < 10) {
    errors.newPassword = "New password must be at least 10 characters.";
  } else if (form.currentPassword && form.newPassword === form.currentPassword) {
    errors.newPassword = "New password must be different from the current password.";
  }
  if (!form.confirmPassword) {
    errors.confirmPassword = "Confirm your new password.";
  } else if (form.newPassword && form.confirmPassword !== form.newPassword) {
    errors.confirmPassword = "Passwords do not match.";
  }
  return errors;
}

export default function ChangePasswordSection() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [alert, setAlert] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const setField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);

    const nextErrors = validate(form);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    setIsSubmitting(true);
    try {
      await changePassword({
        currentPassword: form.currentPassword,
        newPassword: form.newPassword,
      });

      setForm(EMPTY_FORM);
      setAlert({
        type: "success",
        message: "Password changed. Please log in again with your new password.",
      });

      // The backend revokes every session (including this one) on a
      // password change, so the stored token is already dead. Clear
      // local state and send the person back to login rather than
      // leaving them looking at a dashboard that will 401 on next call.
      setTimeout(async () => {
        await logout();
        navigate("/login");
      }, 1500);
    } catch (err) {
      setFormError(err.message || "Could not change password. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="bg-white border border-slate-100 rounded-card p-5 sm:p-6 flex flex-col gap-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-btn bg-bgBlueTint flex items-center justify-center shrink-0">
          <KeyRound className="w-5 h-5 text-primary" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-slate-900">
            Change Password
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Update your own password. You'll need to log in again afterward.
          </p>
        </div>
      </div>

      {alert && (
        <InlineAlert
          type={alert.type}
          message={alert.message}
          onDismiss={() => setAlert(null)}
        />
      )}

      {formError && (
        <div
          role="alert"
          className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2.5"
        >
          {formError}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        noValidate
        className="flex flex-col gap-4 max-w-md"
      >
        <PasswordInput
          id="current-password"
          label="Current Password"
          value={form.currentPassword}
          onChange={(e) => setField("currentPassword", e.target.value)}
          error={errors.currentPassword}
          autoComplete="current-password"
        />

        <PasswordInput
          id="new-password"
          label="New Password"
          value={form.newPassword}
          onChange={(e) => setField("newPassword", e.target.value)}
          error={errors.newPassword}
          autoComplete="new-password"
        />

        <PasswordInput
          id="confirm-password"
          label="Confirm New Password"
          value={form.confirmPassword}
          onChange={(e) => setField("confirmPassword", e.target.value)}
          error={errors.confirmPassword}
          autoComplete="new-password"
        />

        <div className="flex items-center justify-end pt-2 border-t border-slate-100">
          <button
            type="submit"
            disabled={isSubmitting}
            className={`px-3.5 py-2 rounded-btn bg-primary text-white text-sm font-medium hover:bg-blue-700 transition-colors ${
              isSubmitting ? "opacity-70 cursor-not-allowed" : ""
            }`}
          >
            {isSubmitting ? "Changing…" : "Change Password"}
          </button>
        </div>
      </form>
    </section>
  );
}
