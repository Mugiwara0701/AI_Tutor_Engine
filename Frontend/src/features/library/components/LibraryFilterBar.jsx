// src/features/library/components/LibraryFilterBar.jsx
// Placeholder for LibraryFilterBar — implement component/logic here.

// src/features/library/components/LibraryFilterBar.jsx

import FilterBar from "../../../components/shared/FilterBar.jsx";

export default function LibraryFilterBar({
  filterOptions,
  filters,
  onChange,
  onClear,
}) {
  const filterConfig = [
    { key: "class", label: "Class", options: filterOptions.class },
    { key: "subject", label: "Subject", options: filterOptions.subject },
    { key: "book", label: "Book", options: filterOptions.book },
    { key: "status", label: "Status", options: filterOptions.status },
    { key: "updated", label: "Updated", options: filterOptions.updated },
  ];

  return (
    <FilterBar
      filters={filterConfig}
      values={filters}
      onChange={onChange}
      onClear={onClear}
    />
  );
}
