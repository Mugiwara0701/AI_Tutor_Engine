// src/features/sub-topic-order/components/AutoOrderCard.jsx
// Placeholder for AutoOrderCard — implement component/logic here.

// src/features/sub-topic-order/components/AutoOrderCard.jsx

import { Wand2 } from "lucide-react";

export default function AutoOrderCard({ onAutoOrder }) {
  return (
    <div className="bg-white border border-slate-100 rounded-card p-5 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-full bg-bgBlueTint flex items-center justify-center shrink-0">
          <Wand2 className="w-4 h-4 text-primary" />
        </div>
        <p className="text-sm font-semibold text-slate-800">Auto Order</p>
      </div>
      <p className="text-sm text-slate-500">
        Automatically reorder sub topics based on prerequisites — prerequisites
        first, then core concepts, then supporting topics.
      </p>
      <button
        type="button"
        onClick={onAutoOrder}
        className="self-start flex items-center gap-1.5 px-3.5 py-2 rounded-btn border border-primary text-primary text-sm font-medium hover:bg-bgBlueTint transition-colors"
      >
        <Wand2 className="w-4 h-4" />
        Auto Order
      </button>
    </div>
  );
}
