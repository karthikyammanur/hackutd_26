import { useDevice } from "../lib/device";
import type { FeedItem } from "../App";
import { BellIcon, ChatIcon, ChevronRightIcon, SafeSignalMark } from "../components/icons";
import { NoticeContent } from "../components/NoticeContent";
import { TabPage } from "../components/ui";
import { CupArt, SliceArt } from "../components/art";

const RING_RADIUS = 58;
const RING_LENGTH = 2 * Math.PI * RING_RADIUS;
const DATA_USED = 0.16;

function DataRing() {
  return (
    <div className="relative mx-auto size-[148px]">
      <svg viewBox="0 0 148 148" className="size-full -rotate-90" aria-hidden="true">
        <circle cx="74" cy="74" r={RING_RADIUS} fill="none" stroke="#e6e6e6" strokeWidth="12" />
        <circle
          cx="74"
          cy="74"
          r={RING_RADIUS}
          fill="none"
          stroke="var(--color-magenta)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${RING_LENGTH * DATA_USED} ${RING_LENGTH}`}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[36px] font-medium">16%</span>
    </div>
  );
}

export function Home({
  items,
  unread,
  bannerKey,
  onOpenInbox,
  onAsk, onOpenSetup}: {
  items: FeedItem[];
  unread: number;
  bannerKey?: string;
  onOpenInbox: () => void;
  onAsk: () => void;
  onOpenSetup: () => void;
}) {
  const { push } = useDevice();
  // A notice showing as a banner joins this card only after the banner leaves.
  const latest = items.find(
    (item) =>
      item.id !== bannerKey && (item.level === "quiet" || item.level === "warning" || item.level === "summary"),
  );
  return (
    <TabPage tone="bg-page">
      <header className="flex items-center justify-between px-5 pt-[var(--top-clear)]">
        <h1 className="text-[26px] font-bold text-magenta">Hey, Demo</h1>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={onAsk}
            aria-label="Chat and help"
            className="flex size-11 items-center justify-center rounded-lg"
          >
            <ChatIcon />
          </button>
          <button
            type="button"
            onClick={onOpenInbox}
            aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
            className="relative flex size-11 items-center justify-center rounded-lg"
          >
            <BellIcon />
            {unread > 0 && (
              <span className="absolute right-1 top-1 flex size-[18px] items-center justify-center rounded-full bg-magenta text-[11px] font-semibold text-white">
                {unread}
              </span>
            )}
          </button>
        </div>
      </header>
      <p className="mt-2 px-5 text-[15px]">See what's new today</p>

      <section className="mt-5 px-5">
        <h2 className="sr-only">Important alerts</h2>
        {latest ? (
          <button
            type="button"
            onClick={onOpenInbox}
            className={`block w-full rounded-xl border p-3.5 ${
              latest.level === "warning" ? "border-caution/35 bg-[#fffaf2]" : "border-line bg-white"
            }`}
          >
            <NoticeContent level={latest.level} title={latest.notice.title} body={latest.notice.body} />
            <span className="mt-2 block pl-12 text-left text-[14px] font-medium text-magenta">See all notifications</span>
          </button>
        ) : (
          <div className="flex items-center gap-3 rounded-xl border border-line bg-white p-3.5">
            <SafeSignalMark />
            <span>
              <span className="block text-[15px] font-semibold">Safe Signal is on</span>
              <span className="block text-pretty text-[14px] text-muted">We'll tell you if a call needs a second look.</span>
            </span>
          </div>
        )}
        <button
          type="button"
          onClick={onOpenSetup}
          className={`mt-2.5 flex min-h-12 w-full items-center justify-between gap-3 rounded-xl px-3.5 py-2.5 text-left text-[15px] font-semibold ${
            push === "on" ? "border border-line bg-white text-ink" : "bg-magenta text-white"
          }`}
        >
          <span>{push === "on" ? "Notification settings" : "Get warned during a call"}</span>
          <span className="text-[14px] font-medium">{push === "on" ? "On" : "Turn on"}</span>
        </button>
      </section>

      <section className="mt-5 px-5">
        <div className="rounded-xl bg-white p-4 shadow-[0_2px_10px_rgb(0_0_0/0.06)]">
          <h2 className="text-[18px] font-semibold">Your data this month</h2>
          <div className="mt-4">
            <DataRing />
          </div>
          <p className="mt-3 text-center text-[13px] text-muted">of your high-speed data used</p>
          <dl className="mt-4 flex rounded-lg bg-tile py-3 text-center text-white">
            <div className="flex-1 border-r border-white/30">
              <dd className="text-[24px] font-bold leading-7">4.88</dd>
              <dt className="text-[12px]">GB used this month</dt>
            </div>
            <div className="flex-1">
              <dd className="text-[24px] font-bold leading-7">12</dd>
              <dt className="text-[12px]">Days remaining</dt>
            </div>
          </dl>
          <div className="mt-3 flex items-center justify-between py-1 text-[15px] font-medium">
            See usage details
            <ChevronRightIcon size={18} />
          </div>
        </div>
      </section>

      <section className="mt-7">
        <h2 className="px-5 text-[18px] font-semibold">Your perks</h2>
        <ul className="scroller mt-3 flex gap-3 overflow-x-auto px-5">
          <li className="relative h-[172px] w-[240px] shrink-0 overflow-hidden rounded-xl bg-magenta p-4 text-white">
            <p className="text-[13px]">New this week</p>
            <p className="mt-1 text-[20px] font-semibold leading-6">Coffee on us</p>
            <CupArt className="absolute -bottom-3 right-2 size-[108px]" />
          </li>
          <li className="relative h-[172px] w-[240px] shrink-0 overflow-hidden rounded-xl bg-plum p-4 text-white">
            <p className="text-[13px]">Tuesdays</p>
            <p className="mt-1 text-[20px] font-semibold leading-6">A free slice</p>
            <SliceArt className="absolute -bottom-3 right-2 size-[108px]" />
          </li>
        </ul>
      </section>
    </TabPage>
  );
}
