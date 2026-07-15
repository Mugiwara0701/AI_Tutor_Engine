// src/features/settings/components/EmployeeTable.jsx

import { Pencil, Trash2, UserCheck, UserX } from "lucide-react";
import DataTable from "../../../components/ui/DataTable/DataTable.jsx";
import StatusBadge from "../../../components/ui/StatusBadge.jsx";
import UserAvatar from "../../../components/ui/UserAvatar.jsx";
import ActionMenu from "../../../components/ui/ActionMenu.jsx";

export default function EmployeeTable({
  employees,
  onEdit,
  onDelete,
  onToggleStatus,
  canManage = true,
}) {
  const columns = [
    {
      key: "name",
      label: "Employee Name",
      sortable: true,
      render: (row) => (
        <div className="flex items-center gap-3 min-w-0">
          <UserAvatar name={row.name} />
          <span className="font-medium text-slate-800 truncate">
            {row.name}
          </span>
        </div>
      ),
    },
    {
      key: "userId",
      label: "User ID / Username",
      sortable: true,
      render: (row) => <span className="text-slate-500">{row.userId}</span>,
    },
    { key: "role", label: "Role", sortable: true },
    {
      key: "status",
      label: "Status",
      sortable: true,
      render: (row) => <StatusBadge status={row.status} />,
    },
  ];

  // Edit/deactivate/delete are admin-only (backend also enforces this via
  // require_admin), so managers and users get a read-only table instead of
  // buttons that would just 403.
  if (canManage) {
    columns.push({
      key: "actions",
      label: "",
      align: "right",
      render: (row) => (
        <div
          onClick={(e) => e.stopPropagation()}
          className="flex items-center justify-end gap-1"
        >
          <button
            type="button"
            onClick={() => onEdit(row)}
            className="p-1.5 rounded-btn text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            aria-label={`Edit ${row.name}`}
          >
            <Pencil className="w-4 h-4" />
          </button>
          <ActionMenu
            items={[
              {
                label:
                  row.status === "Active" ? "Deactivate" : "Activate",
                icon: row.status === "Active" ? UserX : UserCheck,
                onClick: () => onToggleStatus(row.id),
              },
              {
                label: "Delete",
                icon: Trash2,
                danger: true,
                onClick: () => onDelete(row.id),
              },
            ]}
          />
        </div>
      ),
    });
  }

  return (
    <DataTable
      columns={columns}
      data={employees}
      emptyTitle="No employees added yet"
      emptyDescription="Click “Add Employee” to create the first user account."
    />
  );
}
