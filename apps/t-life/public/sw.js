/* Receives push messages. Shows a system notification unless the app is on screen. */

const ICON = "/icons/icon-192.png";
const BADGE = "/icons/badge-96.png";
const INTERRUPTS = new Set(["urgent", "callback"]);

const ACTIONS = {
  urgent: [
    { action: "open", title: "See what to do" },
    { action: "continue", title: "Continue" },
  ],
  callback: [
    { action: "open", title: "Open" },
    { action: "continue", title: "Not now" },
  ],
};

const VIBRATION = {
  quiet: [40],
  warning: [80, 60, 80],
  summary: [60],
  urgent: [180, 80, 180, 80, 180],
  callback: [400, 120, 400, 120, 400],
};

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

function windows() {
  return self.clients.matchAll({ type: "window", includeUncontrolled: true });
}

self.addEventListener("push", (event) => {
  if (!event.data) return;
  const wire = event.data.json();

  event.waitUntil(
    (async () => {
      const open = await windows();
      const visible = open.filter((client) => client.visibilityState === "visible");
      if (visible.length > 0) {
        visible.forEach((client) => client.postMessage({ type: "notice", notice: wire }));
        return;
      }
      await self.registration.showNotification(wire.notice.title, {
        body: wire.notice.body,
        icon: ICON,
        badge: BADGE,
        tag: wire.id,
        timestamp: wire.at,
        vibrate: VIBRATION[wire.level],
        requireInteraction: INTERRUPTS.has(wire.level),
        actions: ACTIONS[wire.level] ?? [],
        data: wire,
      });
    })(),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // "Continue" must stay one tap: it closes the notification and leaves the call alone.
  if (event.action === "continue") return;
  const wire = event.notification.data;

  event.waitUntil(
    (async () => {
      const [client] = await windows();
      if (client) {
        await client.focus();
        client.postMessage({ type: "open", notice: wire });
        return;
      }
      await self.clients.openWindow(`/?notice=${encodeURIComponent(JSON.stringify(wire))}`);
    })(),
  );
});
