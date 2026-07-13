// src/layouts/Navbar/BreadcrumbNav.jsx

import { useLocation, Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { SIDEBAR_NAV } from "../Sidebar/sidebarConfig.js";

function findBreadcrumbTrail(pathname) {
  for (const item of SIDEBAR_NAV) {
    if (item.path === pathname) {
      if (item.breadcrumbChild) {
        return [
          { label: item.label, path: item.path },
          { label: item.breadcrumbChild, path: item.path },
        ];
      }
      return [{ label: item.label, path: item.path }];
    }

    for (const child of item.children ?? []) {
      if (child.path === pathname) {
        return [
          { label: item.label, path: item.path },
          { label: child.label, path: child.path },
        ];
      }

      const grandchild = child.children?.find((g) => g.path === pathname);
      if (grandchild) {
        return [
          { label: item.label, path: item.path },
          { label: child.label, path: item.path },
          { label: grandchild.label, path: grandchild.path },
        ];
      }
    }

    if (item.children == null && pathname.startsWith(`${item.path}/`)) {
      return [{ label: item.label, path: item.path }];
    }
  }
  return [{ label: "Dashboard", path: "/dashboard" }];
}

export default function BreadcrumbNav() {
  const location = useLocation();
  const trail = findBreadcrumbTrail(location.pathname);

  return (
    <nav
      className="flex items-center gap-1.5 text-sm min-w-0"
      aria-label="Breadcrumb"
    >
      {trail.map((crumb, i) => {
        const isLast = i === trail.length - 1;
        return (
          <span
            key={`${crumb.path}-${i}`}
            className="flex items-center gap-1.5 min-w-0"
          >
            {i > 0 && (
              <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
            )}
            {isLast ? (
              <span className="font-medium text-slate-800 truncate">
                {crumb.label}
              </span>
            ) : (
              <Link
                to={crumb.path}
                className="text-slate-400 hover:text-slate-600 truncate"
              >
                {crumb.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
