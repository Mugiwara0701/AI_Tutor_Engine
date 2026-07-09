// src/features/prompt-studio/components/CompareVersionsModal.jsx

import { useEffect, useState } from "react";
import ModalDialog from "../../../components/ui/ModalDialog.jsx";
import Dropdown from "../../../components/ui/Dropdown.jsx";
import { formatDate } from "../../../utils/formatDate.js";

export default function CompareVersionsModal({ open, onClose, versions }) {
  const [leftVersion, setLeftVersion] = useState(
    versions[1]?.version ?? versions[0]?.version,
  );
  const [rightVersion, setRightVersion] = useState(versions[0]?.version);

  useEffect(() => {
    if (open) {
      setLeftVersion(versions[1]?.version ?? versions[0]?.version);
      setRightVersion(versions[0]?.version);
    }
  }, [open, versions]);

  const options = versions.map((v) => v.version);
  const columns = [
    { version: leftVersion, setVersion: setLeftVersion },
    { version: rightVersion, setVersion: setRightVersion },
  ];

  return (
    <ModalDialog
      open={open}
      onClose={onClose}
      title="Compare Versions"
      maxWidth="2xl"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {columns.map((col, i) => {
          const data = versions.find((v) => v.version === col.version);
          return (
            <div key={i} className="flex flex-col gap-2">
              <Dropdown
                value={col.version}
                onChange={col.setVersion}
                options={options}
                placeholder="Select version"
              />
              {data && (
                <div className="flex flex-col gap-1">
                  <p className="text-xs text-slate-400">
                    {formatDate(data.updatedOn)} — {data.updatedBy?.name}
                  </p>
                  <pre className="bg-[#1E1E2E] text-slate-200 text-xs font-mono rounded-btn p-3 max-h-80 overflow-auto whitespace-pre-wrap leading-5">
                    {data.content}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </ModalDialog>
  );
}
