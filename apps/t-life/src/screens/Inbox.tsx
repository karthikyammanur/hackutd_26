import type { FeedItem } from "../App";
import { CheckIcon } from "../components/icons";
import { NoticeBadge } from "../components/NoticeContent";
import { PushedHeader } from "../components/ui";
import { SUMMARY_NEXT_STEPS } from "../lib/notices";

const TIME = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

function InboxRow({ item }: { item: FeedItem }) {
  return (
    <li className="flex gap-3 border-b border-line py-4">
      <NoticeBadge level={item.level} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[15px] font-semibold leading-5">{item.notice.title}</h2>
          <time className="shrink-0 text-[12px] text-muted">{TIME.format(item.receivedAt)}</time>
        </div>
        <p className="mt-0.5 text-[14px] leading-5 text-muted">{item.notice.body}</p>
        <p className="mt-1 text-[12px] text-muted">
          {item.notice.timing === "during-call" ? "During your call" : "After your call"}
        </p>
        {item.level === "summary" && (
          <ul className="mt-2.5 flex flex-col gap-1.5">
            {SUMMARY_NEXT_STEPS.map((nextStep) => (
              <li key={nextStep} className="flex gap-2 text-[14px] leading-5">
                <CheckIcon size={16} className="mt-0.5 shrink-0 text-ok" />
                {nextStep}
              </li>
            ))}
          </ul>
        )}
        {item.choice && <p className="mt-1.5 text-[13px] font-medium">You chose: {item.choice}</p>}
      </div>
    </li>
  );
}

export function Inbox({ items, onBack }: { items: FeedItem[]; onBack: () => void }) {
  return (
    <main className="min-h-dvh bg-white pb-[calc(env(safe-area-inset-bottom)+76px)]">
      <PushedHeader title="Notifications" onBack={onBack} />
      {items.length === 0 ? (
        <div className="px-5 pt-16">
          <h2 className="text-[24px] font-bold">Nothing here yet</h2>
          <p className="mt-2 text-[15px] text-muted">
            Safe Signal notices land here during and after a call. Send one with the demo control.
          </p>
        </div>
      ) : (
        <ul className="px-5">
          {items.map((item) => (
            <InboxRow key={item.id} item={item} />
          ))}
        </ul>
      )}
    </main>
  );
}
