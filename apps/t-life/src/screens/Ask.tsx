import type { View } from "../App";
import { ChevronRightIcon } from "../components/icons";
import { PushedHeader } from "../components/ui";

export function Ask({
  onBack,
  onGo,
  onOpenInbox,
}: {
  onBack: () => void;
  onGo: (view: View) => void;
  onOpenInbox: () => void;
}) {
  const suggestions = [
    { label: "See my Safe Signal notifications", run: onOpenInbox },
    { label: "Look at this week's perks", run: () => onGo("benefits") },
    { label: "Check my plan and bill", run: () => onGo("account") },
  ];
  return (
    <main className="min-h-dvh bg-white pb-[calc(env(safe-area-inset-bottom)+76px)]">
      <PushedHeader title="Ask" onBack={onBack} />
      <div className="px-5 pt-6">
        <h2 className="text-[28px] font-bold leading-tight">How can we help?</h2>
        <p className="mt-2 text-[15px] text-muted">Pick a suggestion. Typing is turned off in this demo.</p>
        <ul className="mt-6">
          {suggestions.map(({ label, run }) => (
            <li key={label} className="border-b border-line">
              <button type="button" onClick={run} className="flex min-h-14 w-full items-center justify-between gap-3 text-left text-[16px]">
                {label}
                <ChevronRightIcon size={18} />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
