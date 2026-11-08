# Safe Signal notifications: protocol and API reference

Describes the code in `apps/t-life` and `apps/web` as of 2026-11-08.

A notice leaves the console and reaches the device by up to three parallel routes: Web Push, a signed Server-Sent Events stream through ntfy.sh, and HTTP polling. The device removes duplicates by notice `id`.

## 1. What is real and what is scripted

| Part | Status |
|---|---|
| Web Push, SSE stream, polling, storage, signing, encryption | Real and deployed |
| What triggers a notice | Scripted. The console plays a fixed scenario; nothing listens to a real call or calls Jev on this path |
| Notice text | Fixed text from the scenario files. The public route cannot carry free text |
| Who receives it | One shared demo room. Every registered device gets every notice. There are no user accounts or per-customer targeting |
| "Call my bank" and "Ask my trusted contact" | Simulated. They only show a result banner |
| Urgent callback | Simulated. It shows an incoming-call screen and places no phone call |

The WebSocket `UIMessage` stream and Photon notifications in `context/` were plans. Neither is in the notification path, and `services/api` does not exist in this repository.

## 2. Flow

```text
Console browser (apps/web)
  │  scenario beat with a notice is played
  │  POST /tlife-api/notices {scenarioId, beatT}
  ▼
Console Worker "safe-signal"
  │  looks up the fixed text and computes the level
  │  RPC over service binding TLIFE → NoticeRelay.deliver()
  ▼
T-Life Worker "safe-signal-tlife-demo"
  ├─ writes the notice to Workers KV ─────────► GET /api/recent (device polling)
  ├─ encrypts and POSTs to each device's push service ──► service worker on the device
  └─ returns a signed relay message to the console browser
        │  console browser POSTs it to https://ntfy.sh/<topic>
        ▼
     ntfy.sh ── SSE ──► GET https://ntfy.sh/<topic>/sse (open app verifies the signature)
```

The console browser posts to ntfy, not the Worker, because ntfy rate-limits Cloudflare's shared addresses. That post is fire-and-forget. If it fails, push and polling still deliver the notice.

## 3. Endpoints, ports and authentication

Every network connection is HTTPS on TCP 443 (SSE is a long-lived HTTPS GET). There are no custom ports and no WebSockets.

| Service | Address | Protocol | Authentication |
|---|---|---|---|
| T-Life Worker | `https://safe-signal-tlife-demo.berenis-fopa.workers.dev` | HTTPS JSON | None |
| Console Worker | `https://safe-signal.berenis-fopa.workers.dev` | HTTPS JSON | None on `/tlife-api/*` |
| Worker-to-Worker | Binding `TLIFE`, service `safe-signal-tlife-demo`, entrypoint `NoticeRelay` | Cloudflare RPC, no network port | Same Cloudflare account only |
| Live stream | `https://ntfy.sh/ss-tlife-790b250754983806089194c843716637/sse` | SSE | None to read. Messages are signed |
| Live stream publish | `POST https://ntfy.sh/ss-tlife-790b250754983806089194c843716637` | HTTPS | None. Consumers must verify the signature |
| Push services | Origin of each device's `endpoint` | Web Push, HTTPS POST | VAPID (RFC 8292) |

Accepted push endpoints, at most 1024 characters, matching `apps/t-life/worker/hub-endpoints.ts`:

- `https://fcm.googleapis.com/`
- `https://updates.push.services.mozilla.com/`
- `https://*.push.apple.com/`
- `https://*.notify.windows.com/`

### Keys and configuration

| Name | Kind | Purpose |
|---|---|---|
| `VAPID_PUBLIC_KEY` | Public var, also from `GET /api/vapid` | Base64url P-256 point (87 characters) |
| `VAPID_PRIVATE_JWK` | Worker secret | Signs VAPID JWTs |
| `VAPID_SUBJECT` | Var | JWT `sub`: `https://safe-signal-tlife-demo.berenis-fopa.workers.dev` |
| `REALTIME_TOPIC` | Var, also from `GET /api/realtime` | ntfy topic |
| `REALTIME_PUBLIC_KEY` | Public var, also from `GET /api/realtime` | Verifies live-stream signatures. Base64url raw P-256 point (87 characters) |
| `REALTIME_PRIVATE_JWK` | Worker secret | Signs live-stream notices |
| `STORE` | KV namespace `e03a168676524104bbbe32fed913c866` | Subscriptions and recent notices |

## 4. T-Life Worker API

JSON responses use `cache-control: no-store`.

### `GET /api/vapid`

`200 {"publicKey": "<base64url>"}`

### `GET /api/realtime`

`200 {"topic": "<string>", "publicKey": "<base64url>"}`

### `GET /api/recent?since=<epoch ms>`

`200 {"notices": WireNotice[]}`

- Returns room notices with `at > since`, oldest first, at most the newest 12.
- A missing or non-numeric `since` is treated as 0.
- Notices live for 20 minutes.
- Self-test notices are never returned.
- KV reads use a 30-second edge cache, so polling can lag.

### `POST /api/subscribe`

```json
{ "endpoint": "<push URL>", "p256dh": "<base64url>", "auth": "<base64url>" }
```

`p256dh` and `auth` must each be 1 to 256 characters.

| Status | Body | Meaning |
|---|---|---|
| 200 | `{"saved": true}` | Saved, or already identical |
| 503 | `{"saved": false}` | Already 100 devices and this one is new |
| 400 | `{"error": "Invalid keys"}` | Bad `p256dh` or `auth` |
| 400 | `{"error": "Invalid request"}` | Bad JSON, body over 2048 characters, or endpoint rejected |

### `POST /api/unsubscribe`

Body: `{"endpoint": "<push URL>"}`. Returns `200 {"ok": true}`.

### `POST /api/self-test`

Body: `{"endpoint": "<push URL>", "level": "quiet|warning|urgent|summary|callback"}`.

- Returns `202 {"queued": true}`, or `400 {"error": "Unknown level"}`.
- Pushes the matching fixed sample to that one device after 5 seconds.
- An unregistered endpoint still returns 202 and nothing is sent.

Other `/api/*` paths return `404 {"error": "Not found"}`, except that a POST with an invalid body returns 400 first.

### Worker RPC: `NoticeRelay`

Reachable only through the service binding.

```ts
deliver(delivery: NoticeDelivery): Promise<DeliverResult>
status(): Promise<{ phones: number }>

interface DeliverResult {
  phones: number;      // devices whose push service returned 2xx
  limited: boolean;    // room rate limit hit; nothing was sent
  relay?: { url: string; body: string }; // signed message to POST to ntfy
}
```

## 5. Console Worker API

### `POST /tlife-api/notices`

Body, at most 256 characters: `{"scenarioId": "code-request", "beatT": 25}`. `beatT` must exactly match a beat that has a notice.

| Status | Body |
|---|---|
| 200 | `{"phones": 1, "limited": false, "relay": {"url": "https://ntfy.sh/<topic>", "body": "{\"n\":...,\"s\":...}"}}` |
| 429 | `{"phones": 0, "limited": true}` |
| 400 | `{"error": "Expected JSON"}` |
| 404 | `{"error": "No such notice"}` |
| 413 | `{"error": "Request too large"}` |

After a 200, the caller sends `POST relay.url` with `relay.body` as the raw request body.

### `GET /tlife-api/status`

`200 {"phones": <registered devices>}`. The console polls this every 6 seconds while visible.

## 6. Message format

```ts
interface CustomerNotice {
  channel: "t-life" | "urgent-callback";
  timing: "during-call" | "after-call";
  title: string;
  body: string;
}

type NoticeLevel = "quiet" | "warning" | "urgent" | "summary" | "callback";

// Sent over all three routes.
interface WireNotice {
  id: string;     // UUID, created by the T-Life Worker. Deduplication key
  level: NoticeLevel;
  notice: CustomerNotice;
  at: number;     // epoch milliseconds
}
```

Example:

```json
{
  "id": "6f1c2e0a-7a51-4c55-9b5e-0d0c7a7f3f11",
  "level": "urgent",
  "notice": {
    "channel": "t-life",
    "timing": "during-call",
    "title": "This call may be a scam",
    "body": "The caller is asking for a code your bank sent."
  },
  "at": 1794140609000
}
```

## 7. Delivery routes

### Web Push

Payload is the UTF-8 JSON of `WireNotice`, encrypted per RFC 8291.

```http
POST <subscription endpoint>
Authorization: vapid t=<ES256 JWT>, k=<VAPID public key>
Content-Encoding: aes128gcm
Content-Type: application/octet-stream
TTL: 300
Urgency: high
```

| Item | Value |
|---|---|
| JWT header | `{"typ":"JWT","alg":"ES256"}` |
| JWT claims | `aud` = endpoint origin, `exp` = now + 12 hours, `sub` = `VAPID_SUBJECT` |
| Body layout | salt (16 bytes), record size (uint32 big-endian, 4096), key length (1 byte, 65), sender public key (65 bytes), ciphertext |
| Cipher | AES-128-GCM, 16-byte tag, plaintext followed by delimiter byte `0x02`, one record |
| Key exchange | New ephemeral P-256 key and random salt for every message |
| 2xx response | Accepted, counted in `phones` |
| 404 or 410 response | Subscription removed |
| Other response or network error | Not counted, subscription kept. No retry |

Registration on the device:

1. Register `/sw.js`.
2. From a user tap, call `Notification.requestPermission()`.
3. Fetch `GET /api/vapid`.
4. Call `pushManager.subscribe({ userVisibleOnly: true, applicationServerKey })`.
5. Send `POST /api/subscribe`.

The app registers again at launch, when it returns to the screen, and every 15 successful polls.

### Live stream

1. Fetch `GET /api/realtime`.
2. Open `GET https://ntfy.sh/<topic>/sse`.
3. Parse each default SSE `data` frame as JSON and read its `message` string.
4. Parse `message` as `{"n": "<WireNotice JSON string>", "s": "<base64url signature>"}`.
5. Verify `s` over the exact UTF-8 bytes of `n` with ECDSA P-256 and SHA-256.
6. Parse `n`. Drop it if it is more than 2 minutes old.
7. Pass it to the shared deduplicating intake.

Signature format is WebCrypto's: raw `r || s`, 64 bytes, base64url encoded. It is not DER. Malformed or unsigned messages are dropped silently.

The client does not ask ntfy for missed messages. Polling covers gaps.

### Polling

`GET /api/recent?since=<largest at seen>`, only while the app is visible. The first request uses `since=0`.

| Stream state | Interval |
|---|---|
| Closed | 4 seconds |
| Open | 20 seconds |

### Limits

| Limit | Value |
|---|---|
| Registered devices | 100 |
| Notices stored | 40 |
| Notice lifetime | 20 minutes |
| Rate limit | 40 notices in 60 seconds, room and self-test combined |
| `GET /api/recent` result | 12 |
| Push TTL | 300 seconds |

## 8. What triggers a notice

The console sends a notice when all of these are true:

- The call is a test call. Ambient background calls never send.
- The play head moves past a beat that has a `notice`.
- That session has not already sent that beat. Scrubbing back does not resend.

The level is computed in `apps/web/worker/tlife.ts`, first match wins:

| Condition | Level |
|---|---|
| `channel` is `urgent-callback` | `callback` |
| `timing` is `after-call` | `summary` |
| Danger tier is 3 (Severe) or higher | `urgent` |
| Danger tier is 2 (High) | `warning` |
| Anything else | `quiet` |

Tiers run 0 Low, 1 Suspicious, 2 High, 3 Severe, and only rise during a call.

Scripted notices (`t` is seconds into the call; the console defaults to 6x speed):

| Scenario `id` | `t` | Tier | Level | Title | Body |
|---|---|---|---|---|---|
| `code-request` | 25 | 1 | `quiet` | Be careful on this call | This caller isn't on our verified list. |
| `code-request` | 97 | 2 | `warning` | A code just arrived | Don't share it with anyone on this call. |
| `code-request` | 106 | 3 | `urgent` | This call may be a scam | The caller is asking for a code your bank sent. |
| `code-request` | 148 | 3 | `summary` | We checked your last call | It showed signs of a scam. Here's what to do next. |
| `friendly-stranger` | 136 | 2 | `summary` | About your last call | It looked like the start of a friendship scam. Take care before sharing anything. |
| `id-disclosed` | 116 | 3 | `callback` | We need to check something with you | Sensitive details may have been shared on your last call. |

`ordinary-call` sends nothing.

### Fixed self-test and demo samples

`/api/self-test` and the in-app demo control use `DEMO_SEQUENCE`. The first four match `code-request`.

| Level | `channel` | `timing` | Title | Body |
|---|---|---|---|---|
| `quiet` | `t-life` | `during-call` | Be careful on this call | This caller isn't on our verified list. |
| `warning` | `t-life` | `during-call` | A code just arrived | Don't share it with anyone on this call. |
| `urgent` | `t-life` | `during-call` | This call may be a scam | The caller is asking for a code your bank sent. |
| `summary` | `t-life` | `after-call` | We checked your last call | It showed signs of a scam. Here's what to do next. |
| `callback` | `urgent-callback` | `after-call` | Urgent callback from T-Mobile | We're calling about your last call. We won't ask for any code or password. |

## 9. Device behaviour

### Receiving in the service worker

If any app window is visible, the worker posts `{type: "notice", notice: wire}` to it and shows no system notification. Otherwise it calls `showNotification(wire.notice.title, options)`:

| Option | Value |
|---|---|
| `body` | `wire.notice.body` |
| `tag` | `wire.id` |
| `timestamp` | `wire.at` |
| `data` | The whole `WireNotice` |
| `icon` | `/icons/icon-192.png` |
| `badge` | `/icons/badge-96.png` |
| `requireInteraction` | `true` for `urgent` and `callback` |

| Level | System actions (`action`: label) | System vibration (ms) | In-app vibration (ms) |
|---|---|---|---|
| `quiet` | None | 40 | 30 |
| `warning` | None | 80, 60, 80 | 70, 50, 70 |
| `summary` | None | 60 | 50 |
| `urgent` | `open`: See what to do; `continue`: Continue | 180, 80, 180, 80, 180 | 160, 70, 160 |
| `callback` | `open`: Open; `continue`: Not now | 400, 120, 400, 120, 400 | 320, 100, 320 |

### Tapping a notification

- Action `continue` closes the notification and does nothing else.
- Otherwise, an existing window is focused and receives `{type: "open", notice: wire}`.
- With no window, the app opens at `/?notice=<URL-encoded WireNotice JSON>`. This launch parameter is not signature-checked.
- After opening, `urgent` and `callback` show their full-screen view. Other levels open the inbox.

### Intake, deduplication and staleness

- A session-memory set of `id`s drops repeats across all routes.
- The inbox is stored in `localStorage` under `tlife-demo-feed`, at most 30 items.
- On the first poll, a notice is added silently to the inbox unless it is an `urgent` or `callback` that is at most 90 seconds old.
- An unanswered takeover older than 90 seconds comes back as an inbox item only.

### How each level appears

| Level | Presentation | Ends when |
|---|---|---|
| `quiet` | Banner, then inbox | 6 seconds, swipe, or dismiss |
| `warning` | Banner, then inbox | Swipe or dismiss |
| `summary` | Banner, then inbox with next steps | Swipe or dismiss |
| `urgent` | Full-screen takeover, recorded in inbox | Customer picks a button |
| `callback` | Simulated incoming-call screen, recorded in inbox | Customer answers then ends, or picks Not now |

Up to 4 banners are queued. Tapping a banner opens the inbox and marks everything read.

### Fixed text around each notice

**Banner:** `Safe Signal`, `now`, then title and body. When more are queued: `<n> more`.

**Urgent screen:**

- Above the title: `On your call with (214) 555-0142`
- Title and body from the notice
- `Your call stays on. You decide what happens next.`
- Buttons: `Call my bank`, `Ask my trusted contact`, `Continue`

| Button | Result |
|---|---|
| Call my bank | Demo only, no call placed. The real app would open your dialer with the number on your card. Your current call stays on. |
| Ask my trusted contact | Demo only, no message sent. The real app would reach your trusted contact. Your current call stays on. |
| Continue | Closes with no message |

**Callback screen:**

- Status: `Incoming call`, then `Connected`
- Title from the notice
- Number: `(800) 555-0199`
- Body from the notice
- `This callback only reaches you. It doesn't contact emergency services.`
- Buttons: `Not now`, `Answer`, then `End call`. The recorded choice is `Not now` or `Answered`

**Inbox item:** title, time, body, then `During your call` or `After your call`. If the customer chose an action: `You chose: <choice>`.

**Summary next steps:**

1. Call your bank using the number on your card.
2. Change any password or code you shared on the call.
3. Answer our callback if you'd like help with the next steps.

## 10. Rules any client must keep

From `context/rules.md` and the notice code:

- Never hang up automatically. The top level is an alert with three buttons.
- `Continue` must stay one tap and must leave the call alone.
- The callback never contacts emergency services.
- Notices carry no transcript text. Text is plain reasons and next steps.

## 11. Browser-only parts

| Part | Reusable outside a browser? |
|---|---|
| `GET /api/recent` polling | Yes, plain HTTPS |
| ntfy SSE stream and signature check | Yes. Non-browser crypto libraries often default to DER signatures, so convert from raw `r || s` |
| `WireNotice` format and level rules | Yes |
| `/api/subscribe` and Web Push | Browser only as built. The server needs a real Web Push subscription (`endpoint`, `p256dh`, `auth`) from the allowed push services. A native push token is not one |
| `sw.js`, `showNotification`, `/?notice=` launch | Browser only. These need native equivalents |
| `localStorage` inbox | Browser only |

## Source files

| File | Contents |
|---|---|
| `apps/t-life/worker/index.ts` | T-Life HTTP routes and `NoticeRelay` |
| `apps/t-life/worker/hub.ts` | Storage, limits, fan-out, self-test |
| `apps/t-life/worker/webpush.ts` | RFC 8291 encryption, VAPID, push send |
| `apps/t-life/worker/realtime.ts` | Notice signing and relay message |
| `apps/t-life/src/lib/device.ts` | Registration, polling, SSE, launch handling |
| `apps/t-life/src/lib/delivery.ts` | Deduplication and staleness |
| `apps/t-life/src/lib/notices.ts` | Types and fixed text |
| `apps/t-life/public/sw.js` | Push and notification-click handling |
| `apps/web/worker/tlife.ts` | Console route and level rules |
| `apps/web/src/hooks/useCallSessions.ts` | When the console sends, and the ntfy post |
| `apps/web/src/lib/console/call-model.ts`, `scenarios.ts` | Scripted notices |
