import { useCallback, useEffect, useState } from "react";
import { Banner, type BannerContent } from "./components/Banner";
import { CallbackScreen } from "./components/CallbackScreen";
import { DemoControl } from "./components/DemoControl";
import { DemoMarker } from "./components/DemoMarker";
import { TabBar, type Tab } from "./components/TabBar";
import { UrgentScreen } from "./components/UrgentScreen";
import { NotificationSheet } from "./components/NotificationSheet";
import { deliverNotice, isStillUrgent, rememberSeen, subscribeToNotices, subscribeToOpens } from "./lib/delivery";
import { startDevice } from "./lib/device";
import { DEMO_SEQUENCE, type DeliveredNotice, type UrgentAction } from "./lib/notices";
import { Account } from "./screens/Account";
import { Ask } from "./screens/Ask";
import { Benefits } from "./screens/Benefits";
import { Home } from "./screens/Home";
import { Inbox } from "./screens/Inbox";
import { Services } from "./screens/Services";
import { Shop } from "./screens/Shop";

export type View = Tab | "inbox" | "ask";

export interface FeedItem extends DeliveredNotice {
  read: boolean;
  choice?: string;
}

const QUIET_BANNER_MS = 6000;
const MAX_BANNERS = 4;
const FEED_KEY = "tlife-demo-feed";
const MAX_FEED = 30;

const VIBRATION: Partial<Record<DeliveredNotice["level"], number[]>> = {
  quiet: [30],
  warning: [70, 50, 70],
  summary: [50],
  urgent: [160, 70, 160],
  callback: [320, 100, 320],
};

const interrupts = (level: DeliveredNotice["level"]) => level === "urgent" || level === "callback";

/** The inbox survives closing the app. An old unanswered takeover comes back as an inbox item only. */
function loadFeed(): FeedItem[] {
  try {
    const items = JSON.parse(localStorage.getItem(FEED_KEY) ?? "[]") as FeedItem[];
    const now = Date.now();
    rememberSeen(items.map((item) => item.id));
    return items.map((item) => (isStillUrgent(item.receivedAt, now) ? item : { ...item, muted: true }));
  } catch {
    return [];
  }
}

function saveFeed(items: FeedItem[]) {
  try {
    localStorage.setItem(FEED_KEY, JSON.stringify(items.slice(0, MAX_FEED)));
  } catch {
    // Private windows can refuse storage. The inbox still works until the app closes.
  }
}

const ACTION_RESULTS: Record<Exclude<UrgentAction, "Continue">, string> = {
  "Call my bank":
    "Demo only, no call placed. The real app would open your dialer with the number on your card. Your current call stays on.",
  "Ask my trusted contact":
    "Demo only, no message sent. The real app would reach your trusted contact. Your current call stays on.",
};

export default function App() {
  const [view, setView] = useState<View>("home");
  const [feed, setFeed] = useState<FeedItem[]>(loadFeed);
  const [banners, setBanners] = useState<BannerContent[]>([]);
  const [step, setStep] = useState(0);
  const [setupOpen, setSetupOpen] = useState(false);
  const banner = banners[0] ?? null;

  useEffect(() => saveFeed(feed), [feed]);

  useEffect(() => {
    const stopNotices = subscribeToNotices((delivered) => {
      setFeed((items) => [{ ...delivered, read: false }, ...items]);
      if (delivered.muted) return;
      navigator.vibrate?.(VIBRATION[delivered.level] ?? []);
      if (interrupts(delivered.level)) return;
      const next: BannerContent = {
        key: delivered.id,
        level: delivered.level,
        title: delivered.notice.title,
        body: delivered.notice.body,
      };
      setBanners((current) => [next, ...current].slice(0, MAX_BANNERS));
    });
    const stopOpens = subscribeToOpens((delivered) => {
      if (interrupts(delivered.level)) return;
      setFeed((items) => items.map((item) => ({ ...item, read: true })));
      setBanners([]);
      setView("inbox");
      window.scrollTo(0, 0);
    });
    // After the listeners, so a notice that launched the app isn't missed.
    const stopDevice = startDevice();
    return () => {
      stopNotices();
      stopOpens();
      stopDevice();
    };
  }, []);

  const dismissBanner = useCallback((key: string) => {
    setBanners((current) => current.filter((item) => item.key !== key));
  }, []);

  // Only quiet banners leave by themselves. They stay in the inbox and on Home.
  const quietBannerKey = banner?.level === "quiet" ? banner.key : null;
  useEffect(() => {
    if (!quietBannerKey) return;
    const timer = window.setTimeout(() => dismissBanner(quietBannerKey), QUIET_BANNER_MS);
    return () => window.clearTimeout(timer);
  }, [quietBannerKey, dismissBanner]);

  const resolve = useCallback((id: string, choice: string) => {
    setFeed((items) => items.map((item) => (item.id === id ? { ...item, choice } : item)));
  }, []);

  const handleUrgentAction = useCallback(
    (id: string, action: UrgentAction) => {
      resolve(id, action);
      if (action !== "Continue") {
        const result: BannerContent = { key: `${id}-${action}`, level: "quiet", title: action, body: ACTION_RESULTS[action] };
        setBanners((current) => [result, ...current].slice(0, MAX_BANNERS));
      }
    },
    [resolve],
  );

  const openInbox = useCallback(() => {
    setFeed((items) => items.map((item) => ({ ...item, read: true })));
    setBanners([]);
    setView("inbox");
    window.scrollTo(0, 0);
  }, []);

  const go = useCallback((next: View) => {
    setView(next);
    window.scrollTo(0, 0);
  }, []);

  const fireNext = () => {
    if (step >= DEMO_SEQUENCE.length) {
      setFeed([]);
      setBanners([]);
      setStep(0);
      go("home");
      return;
    }
    deliverNotice(DEMO_SEQUENCE[step]);
    setStep(step + 1);
  };

  const overlay = feed.find((item) => interrupts(item.level) && !item.choice && !item.muted);
  const unread = feed.filter((item) => !item.read).length;
  const inCall = feed[0]?.notice.timing === "during-call" && !feed[0].muted;
  const pushed = view === "inbox" || view === "ask";

  return (
    <>
      <div inert={overlay ? true : undefined}>
        {view === "home" && <Home items={feed} unread={unread} bannerKey={banner?.key} onOpenInbox={openInbox} onAsk={() => go("ask")} onOpenSetup={() => setSetupOpen(true)} />}
        {view === "shop" && <Shop />}
        {view === "benefits" && <Benefits />}
        {view === "services" && <Services onOpenInbox={openInbox} />}
        {view === "account" && <Account />}
        {view === "inbox" && <Inbox items={feed} onBack={() => go("home")} />}
        {view === "ask" && <Ask onBack={() => go("home")} onGo={go} onOpenInbox={openInbox} />}

        {!pushed && <TabBar active={view} onSelect={go} onAsk={() => go("ask")} />}
        <DemoControl step={step} pushed={pushed} visible={!overlay} onFire={fireNext} />
      </div>

      {banner && !overlay && (
        <Banner
          key={banner.key}
          content={banner}
          behind={banners.length - 1}
          autoDismissMs={banner.level === "quiet" ? QUIET_BANNER_MS : null}
          onOpen={openInbox}
          onDismiss={() => dismissBanner(banner.key)}
        />
      )}

      {setupOpen && <NotificationSheet onClose={() => setSetupOpen(false)} />}

      {overlay?.level === "urgent" && (
        <UrgentScreen
          key={overlay.id}
          notice={overlay.notice}
          onAction={(action) => handleUrgentAction(overlay.id, action)}
        />
      )}
      {overlay?.level === "callback" && (
        <CallbackScreen key={overlay.id} notice={overlay.notice} onDone={(choice) => resolve(overlay.id, choice)} />
      )}

      <DemoMarker inCall={inCall} />
    </>
  );
}
