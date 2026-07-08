// src/hooks/useKeyboardShortcut.js
// Placeholder for useKeyboardShortcut — implement component/logic here.

import { useEffect } from "react";

/**
 * Fires `callback` when the given key is pressed together with Cmd (Mac) or
 * Ctrl (Windows/Linux). Example: useKeyboardShortcut("k", () => focusSearch())
 */
export function useKeyboardShortcut(key, callback) {
  useEffect(() => {
    function handleKeyDown(e) {
      const isModifierPressed = e.metaKey || e.ctrlKey;
      if (isModifierPressed && e.key.toLowerCase() === key.toLowerCase()) {
        e.preventDefault();
        callback(e);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [key, callback]);
}
