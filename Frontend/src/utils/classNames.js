// src/utils/classNames.js
// Placeholder for classNames — implement component/logic here.
/**
 * Tiny classnames helper — joins truthy class strings and skips falsy values.
 * Usage: cn("btn", isActive && "btn-active", className)
 */
export function cn(...classes) {
  return classes.filter(Boolean).join(" ");
}
