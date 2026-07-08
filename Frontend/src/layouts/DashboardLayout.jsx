// src/layouts/DashboardLayout.jsx
// Placeholder for DashboardLayout — implement component/logic here.

import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar/Sidebar.jsx";
import Navbar from "./Navbar/Navbar.jsx";
import { SidebarProvider } from "../context/SidebarContext.jsx";

export default function DashboardLayout() {
  return (
    <SidebarProvider>
      <div className="min-h-screen flex bg-bgLight">
        <Sidebar />
        <div className="flex-1 min-w-0 flex flex-col">
          <Navbar />
          <main className="flex-1 min-w-0 p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
