import type { DeletionReceipt as Receipt } from "@/hooks/useCallSessions";
import { formatClock } from "@/lib/console/format";
import { Icon } from "../../icons";

export function DeletionReceipt({ receipt, onClose }: { receipt: Receipt; onClose: () => void }) {
  const rows: [string, string][] = [
    ["What was held", "The conversation window in memory, the danger markers, and the number for this session."],
    ["How long", `${formatClock(receipt.heldSeconds)} of call time, from the start of the call until deletion.`],
    ["Where it is now", "Erased from the pipeline. No call log was kept."],
  ];

  return (
    <div className="animate-rise rounded-[20px] bg-white p-6 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2.5 text-[17px] font-semibold tracking-[-0.012em]">
          <span className="grid size-7 flex-none place-items-center rounded-full bg-[#E2EADB] text-[#5C7A48]">
            <Icon name="tick" />
          </span>
          Deletion receipt
        </h3>
        <button type="button" onClick={onClose} className="text-[13px] font-medium text-ink-2 hover:text-ink">
          Close
        </button>
      </div>
      <dl className="mt-4 grid gap-y-3 border-t border-dashed border-wire pt-3.5">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-[13px] text-ink-2">{label}</dt>
            <dd className="mt-px font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3.5 text-[12.5px] text-ink-2">
        {receipt.sentNotices && "Notices already delivered stay on the customer's phone. "}
        This review exists only on this screen. It's gone the moment you move on or reload.
      </p>
    </div>
  );
}
