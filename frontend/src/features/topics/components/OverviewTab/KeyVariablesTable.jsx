// src/features/topics/components/OverviewTab/KeyVariablesTable.jsx
// Placeholder for KeyVariablesTable — implement component/logic here.

// src/features/topics/components/OverviewTab/KeyVariablesTable.jsx

export default function KeyVariablesTable({ variables = [] }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-4">
      <h3 className="text-sm font-semibold text-slate-900 mb-3">
        Key Variables
      </h3>
      <table className="w-full text-sm">
        <tbody>
          {variables.map((v) => (
            <tr
              key={v.symbol}
              className="border-t border-slate-50 first:border-t-0"
            >
              <td className="py-2 pr-3 w-16">
                <span className="inline-flex items-center justify-center w-8 h-8 rounded-btn bg-blue-50 text-primary font-semibold text-sm">
                  {v.symbol}
                </span>
              </td>
              <td className="py-2 text-slate-600">{v.name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
