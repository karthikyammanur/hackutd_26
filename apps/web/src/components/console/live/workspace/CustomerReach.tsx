import type { Beat, CallTrace, CustomerNotice } from "@/lib/console/call-model";
import type { NoticeDelivery } from "@/hooks/useCallSessions";
import { formatClock } from "@/lib/console/format";

function deliveryLabel(delivery: NoticeDelivery): { text: string; dot: string } {
  if (delivery.state === "sending") return { text: "Sending to T-Life", dot: "bg-white/60 animate-pulse" };
  if (delivery.state === "failed") return { text: "Couldn't reach T-Life", dot: "bg-[#FFD3E9]" };
  return { text: "Sent to T-Life", dot: "bg-white" };
}

function DeliveryLine({ delivery }: { delivery: NoticeDelivery }) {
  const { text, dot } = deliveryLabel(delivery);
  return (
    <p role="status" className="mt-3 inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-[13px] font-medium text-white">
      <i className={`size-2 flex-none rounded-full ${dot}`} aria-hidden="true" />
      {text}
    </p>
  );
}

function sentLabel(notice: CustomerNotice): string {
  if (notice.channel === "urgent-callback") return "Urgent callback placed";
  return notice.timing === "after-call" ? "Customer notified in T-Life after the call" : "Customer notified in T-Life";
}

/** What the system has done to reach the customer. Staff watch this; they can't act from it. */
export function CustomerReach({
  trace,
  deliveryAt,
}: {
  trace: CallTrace;
  deliveryAt: (beatT: number) => NoticeDelivery | undefined;
}) {
  const sent = trace.past.filter((beat): beat is Beat & { notice: CustomerNotice } => beat.notice !== undefined);
  const latest = sent.at(-1);

  if (!latest) {
    return (
      <div className="rounded-[20px] bg-white p-6 shadow-soft">
        <h3 className="text-[21px] leading-[1.2] font-semibold tracking-[-0.02em]">Nothing sent to the customer</h3>
        <p className="mt-2 text-[14.5px] text-ink-2">Safe Signal stays quiet unless something looks wrong.</p>
      </div>
    );
  }

  const earlier = sent.slice(0, -1).reverse().slice(0, 2);
  const latestDelivery = deliveryAt(latest.t);
  const calling = sent.some((beat) => beat.notice.channel === "urgent-callback");

  return (
    <div className="rounded-[20px] bg-alert p-6 text-white shadow-[0_14px_32px_rgba(226,0,116,0.26)]">
      <h3 className="text-[21px] leading-[1.2] font-semibold tracking-[-0.02em]">{sentLabel(latest.notice)}</h3>
      <p className="mt-2 text-[14.5px] text-[#FFE7F3]">
        {latest.notice.title}. {latest.notice.body}
      </p>
      {latestDelivery && <DeliveryLine delivery={latestDelivery} />}
      {earlier.length > 0 && (
        <ul className="mt-3.5 border-t border-white/25 pt-2.5 text-[13px] text-[#FFE7F3]">
          {earlier.map((beat) => (
            <li key={beat.t} className="flex justify-between gap-3 py-0.5">
              <span className="min-w-0 truncate">{beat.notice.title}</span>
              <span className="flex-none tabular-nums">{formatClock(beat.t)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3.5 text-[12.5px] text-[#FFD3E9]">
        {calling ? "We phone the customer, never emergency services." : "The customer decides. Safe Signal never hangs up."}
      </p>
    </div>
  );
}
