// src/layouts/Sidebar/sidebarConfig.js
// Placeholder for sidebarConfig — implement component/logic here.

import {
  LayoutDashboard,
  Library,
  Share2,
  Code2,
  Archive,
  Activity,
  HardDrive,
  BarChart3,
  Search,
  Settings,
} from "lucide-react";

// Single source of truth for sidebar navigation AND breadcrumb generation.
// Each item: { key, label, icon, path, children? }
export const SIDEBAR_NAV = [
  {
    key: "dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    path: "/dashboard",
  },
  {
    key: "library",
    label: "Library",
    icon: Library,
    path: "/library",
    children: [
      { key: "library-all", label: "All Content", path: "/library" },
      { key: "library-classes", label: "Classes", path: "/library/classes" },
      { key: "library-subjects", label: "Subjects", path: "/library/subjects" },
      { key: "library-topics", label: "Topics", path: "/library/topics" },
      { key: "library-books", label: "Books", path: "/library/books" },
    ],
  },
  {
    key: "learning-graph",
    label: "Learning Graph",
    icon: Share2,
    path: "/learning-graph",
  },
  {
    key: "prompt-studio",
    label: "Prompt Studio",
    icon: Code2,
    path: "/prompt-studio",
  },
  {
    key: "zip-manager",
    label: "ZIP Manager",
    icon: Archive,
    path: "/zip-manager",
  },
  {
    key: "pipeline-monitor",
    label: "Pipeline Monitor",
    icon: Activity,
    path: "/pipeline-monitor",
  },
  {
    key: "storage-explorer",
    label: "Storage Explorer",
    icon: HardDrive,
    path: "/storage-explorer",
  },
  { key: "analytics", label: "Analytics", icon: BarChart3, path: "/analytics" },
  {
    key: "global-search",
    label: "Global Search",
    icon: Search,
    path: "/search",
  },
  { key: "settings", label: "Settings", icon: Settings, path: "/settings" },
];
