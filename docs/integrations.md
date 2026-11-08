# Integrations: Photon, ElevenLabs, sidecar

How the live demo reaches a real phone. Owner: Lane 4. Decisions behind this: F8 in `context/decisions.md`.

## The one rule: the customer texts the Photon line first

Our Photon iMessage line is **+1 628-998-8619**. It is a *shared* line, and a shared line can only message
someone who has texted it. So before any demo run:

1. On the phone in `DEMO_CUSTOMER_NUMBER`, text **"hi"** to **+1 628-998-8619**.
2. Do not text the number that called you (ending 4814). That is the ElevenLabs voice line and it does not
   receive texts.

After that, alerts and messages reach the phone. iPhones get iMessage; Android gets RCS or SMS (tested
2026-11-08: an alert reached an Android phone and its reply "1" came back with `metadata.transport=rcs`).
If an iPhone user switched to Android and messages never arrive, their number is probably still registered
with iMessage. Turn iMessage off on the old device, or deregister at selfsolve.apple.com/deregister-imessage.

Every outbound message and call goes to `DEMO_CUSTOMER_NUMBER`, whatever role the graph names (customer or
trusted contact). Only teammates' own numbers (R10).

## How the pieces connect

```
graph (Lane 1) --Tools--> PhotonComms --HTTP--> sidecar (Node) --Photon REST--> customer's phone
                          ElevenLabsVoice --ElevenLabs SIP trunk--> customer's phone (bank callback)
customer replies "1" --> sidecar polls Photon --> POST API_URL/sessions/{id}/choice {"choice": "call_bank", "digit": "1"}
```

`services.agents.tools.real_tools()` builds this set: `PhotonComms`, `ElevenLabsVoice`, `DemoStore`
(in memory), `SimAccount` (simulated holds), and Lane 1's stand-in decider until Lane 2's lands.
`services.agents.tools.mock.mock_tools()` gives in-memory fakes with no network.

## Start the sidecar

```
cd spikes/photon
npm install            # first time only
npm run sidecar        # listens on PHOTON_SIDECAR_URL's port (default 8787), localhost only
curl http://localhost:8787/health
```

It reads `../../.env`. The API (`API_URL`) must be running for replies to be forwarded; without it the sidecar
logs `API_URL unset, not posted` and does nothing else.

Sidecar endpoints:

| Endpoint | Body | Does |
| --- | --- | --- |
| `POST /notify` | `{to, text, session_id, choices, buttons}` | Sends the alert; sets what replies 1/2/3 mean |
| `POST /message` | `{to, text, session_id}` | Sends a text; keeps the current reply menu |
| `GET /health` | | Current session, masked number, whether `API_URL` is set |

Replies: the sidecar polls Photon every 2 s for messages from the last number it messaged, on any platform.
A bare `1`, `2` or `3` (also `1.`, `2)`) becomes the matching button id from the last `/notify`, in order
`call_bank`, `ask_trusted_contact`, `continue`. Anything else is logged as "not a choice". It never logs
message text (R8).

## What each tool does live

| Graph call | Live behaviour |
| --- | --- |
| `comms.notify` | Alert text + "Reply 1 to ..." menu, via sidecar `/notify` |
| `comms.message` | Text via sidecar `/message` |
| `voice.whisper` | Sent as a text via sidecar `/message`: we cannot inject audio into a live call (F8) |
| `comms.call` | ElevenLabs outbound call from the **Safe Signal Follow-up** agent to `DEMO_CUSTOMER_NUMBER`. The script is passed as dynamic variable `{{callback_script}}`; the agent's first message is `{{callback_script}}`, so it opens with our script word for word |
| `comms.transfer` | Our code still cannot transfer a live call (F8). The follow-up agent does it: its `transfer_to_number` tool (conference) calls `DEMO_BANK_NUMBER` only when the customer clearly says yes. `PhotonComms.transfer` just records `agent-transfer-on-yes:<call id>` for that number; any other number raises `ToolUnsupported` (step failed, call untouched, R4). Untested on a live call; on our SIP number the customer may hear silence while the bank phone rings (ElevenLabs plays a hold message only on Twilio numbers) |
| `store.*` | `DemoStore`, in memory; drops `turn` events (R8). `DEMO_BANK_NUMBER` is Lone Star Bank's verified number (spoken in the script and used as the transfer destination) |
| `account.hold_changes` | `SimAccount`: logs a simulated hold |

The callback refuses to run (`ToolConfigError`, nothing dialed) if `ELEVENLABS_BANK_AGENT_ID` is unset or
equals `SCAMMER_AGENT_ID`. Nothing ever dials 911, 988 or 112 (R1).

## Live demo: the card-fraud call, cut at three points

One script (agent "Safe Signal Scammer Sim (Hero 1)", `SCAMMER_AGENT_ID`): Lone Star Bank fraud desk, flagged
charge, "don't hang up", then asks for the card number, expiry and security code. The run ends where you cut it:

| Run | Customer | What happens |
| --- | --- | --- |
| S1 | Sees the APK's scam-call warning and declines | Nothing else runs (no turns, no alerts) |
| S2 | Answers, hears the card ask, gets the alert, hangs up | `alert` the moment the card is asked for -> APK `urgent`. After the call: lock account, recovery, evidence. **No callback** |
| S3 | Answers and reads out a card (use a fake one: 4242 4242 4242 4242, 12/28, 123) | Same alert, then the **callback** call offering the bank (follow-up agent, `transfer_to_number` to `DEMO_BANK_NUMBER`) |

- **Start a call:** "Place real call" in the console's Live window (setup below), or from a terminal
  `python spikes/live_bridge.py --yes`. Both call `POST /calls/start` (no body; it always dials
  `DEMO_CUSTOMER_NUMBER`, R10). The API follows the call itself (`services/api/live_call.py`), one at a time.
  The console also picks up a call started from the terminal (`GET /calls/current`, every 5 s).
- **Alerts to the Intercept APK** go through Berny's T-Life path, exactly like test calls, and the open console
  page sends them. When a real call first reaches a whisper alert, a full alert, recovery sent or callback placed,
  the page posts `/tlife-api/notices` with scenario `live-card-fraud` and that notice's beat. The text is written in
  advance (`LIVE_NOTICES` in `apps/web/src/lib/console/scenarios.ts`), so no route carries free text:

  | Moment | T-Life level | Title |
  | --- | --- | --- |
  | Whisper alert | `warning` | Be careful on this call |
  | Full alert | `urgent` | Stop: this call is a scam |
  | Recovery sent | `summary` | After your call: what to do now |
  | Callback placed | `callback` | Safe Signal is calling you |

  Each goes once per call; nudges send nothing. The console shows "Sent to T-Life" or "Couldn't reach T-Life" on
  each one. iMessage alerts (Photon, sent by the API) go out as before.
- **S1 needs the APK's scam number** set to the ElevenLabs caller ID (the number on `ELEVENLABS_PHONE_NUMBER_ID`).
- **Did they hand it over?** The after-call planner reads the full transcript (memory only) and the code counts the
  digits the customer said. Callback only when the customer read out digits, or pressed "call my bank". The
  planner's own "yes" needs at least a few customer digits (it once claimed a disclosure that never happened).
  The transcript is erased when the after-call work ends, or at call end when none runs. Never written to disk (R8).

## Run it from the hosted console

```
console page (safe-signal.berenis-fopa.workers.dev)
  --/live-api, the Worker adds the token--> tunnel --> API on Berny's laptop --> ElevenLabs (calls), Photon (iMessage)
  --/tlife-api, pre-written notices------> T-Life demo worker --> Intercept APK
```

The browser never talks to the API itself. The console's Worker (`apps/web/worker/live-proxy.ts`) exposes four
routes only: `POST /calls/start`, `GET /calls/current`, `GET /sessions/{id}/view`, `GET /health`. The view
(`services/api/view.py`) is markers only: kinds, times, levels, the alert sentence and step statuses. No turn text,
quotes or numbers reach the public site. The console polls it every second.

Already hosted, nothing to do: the T-Life demo worker, Nemotron (Brev), ElevenLabs and Photon.

**Berny's laptop runs the backend during the demo:**

1. **`.env`** is not in git: get it privately. It holds the ElevenLabs, Photon, Nemotron and demo numbers, plus
   `API_TOKEN` (make one with `python -c "import secrets; print(secrets.token_urlsafe(24))"`) and `TOOLS=real`.
   With `API_TOKEN` set, every console route needs `Authorization: Bearer <token>` (the WebSocket takes `?token=`).
   Left open: `/health`, `/sessions/{id}/choice` (the sidecar) and `/live/sms` (the phone), which carry only a choice
   or a sender type. Live session ids are random, so a choice can't be aimed at a call.
2. **Python dependencies:** `pip install -e .` from the repo root.
3. **API:** `uvicorn services.api.main:app --port 8000`. Check `http://localhost:8000/health`: `tools: real` and both
   Nemotron tiers true.
4. **Photon sidecar:** `cd spikes/photon && npm install && npm run sidecar` (see above).
5. **Tunnel:** `cloudflared tunnel --url http://localhost:8000`. A quick tunnel gets a new URL every restart, so
   step 6 has to be redone each time; a named Cloudflare tunnel or an ngrok static domain keeps one URL. The same URL
   goes in the call-screener app's "API address" box.

**Berny redeploys the console** (an update to the Worker he already hosts), on his Mac:

6. Pull `l4-5-live-bridge`, then `cd apps/web && npm ci`. `npx wrangler secret put LIVE_API_TOKEN` (the same value as
   `API_TOKEN`), set `LIVE_API_URL` in `wrangler.jsonc` to the tunnel URL, then `npm run deploy`.

**Before each run:** the customer's phone has texted "hi" to the Photon line (top of this page).

**During the run, keep the console page open and on screen, on the Live view, until the after-call steps finish**
(the call shows "Call data deleted"). That page sends the APK notices: closed, hidden or on another view, they
don't go out. Use one console tab only (each open tab sends its own copy) and don't reload it mid-call (a reload
sends the notices again).

The command bar shows "Rings the demo phone from the scammer line" when the console can reach the API, or why not
("The live API isn't configured", "The console's token doesn't match the API's", "The live API isn't reachable").
Anyone who can open the console can press the button while the API is up, so stop the tunnel after the demo.

## Hero 1 with a real bank code

1. **Scammer call -> API.** `python spikes/live_bridge.py --yes` (or the console button, above).
2. **Bank code -> API.** The call-screener app (`spikes/call-screener`) now listens for incoming texts. A text
   with a 4-8 digit code and a code word is reported as `POST /live/sms {"sender_type", "org"}`: a 5-6 digit
   sender is a short code, `bank_shortcode` when the text names a bank. The code and the text never leave the
   phone. The API attaches it to the newest live call; no live call, it is ignored.
3. **Trigger a real bank code** during the call (e.g. "forgot password" or sign-in on a real bank's site).
   Only `bank_shortcode` counts, so a teammate texting a code from their own number will not trigger it.
   **Never read the real code aloud**: ElevenLabs keeps the scammer call's transcript.
4. The phone reaches the API through a tunnel (`ngrok http 8000`): set the URL in the app's
   "API address" box, or `SAFE_SIGNAL_PHONE_API_URL` in `.env` before building. `/live/sms` needs no token.
   Set `API_TOKEN` before opening the tunnel: without it, `WS /ws/{id}` (live turn text) is open to anyone.

## Spikes and checks

| Command | Real send? |
| --- | --- |
| `python spikes/elevenlabs_check.py` | No. Lists agents and phone numbers |
| `cd spikes/photon && npm run check` | No. Photon login + demo space |
| `cd spikes/photon && npm run send` | No (dry run). Add `-- --yes` to send one message |
| `python spikes/elevenlabs_call.py` | No (dry run). Add `--yes` to place one scammer call |
| `cd spikes/photon && npm test && npm run typecheck` | No |
| `python -m pytest services/agents/tools` | No. Fake HTTP only |

## Env vars

| Var | Used by | Notes |
| --- | --- | --- |
| `PHOTON_PROJECT_ID`, `PHOTON_API_KEY` | sidecar, spikes | Photon REST project and key |
| `PHOTON_AGENT_USER_ID` | sidecar, spikes | Our line's Photon user (`pho_usr_...`) |
| `PHOTON_SPACE_ID` | `check.ts` | The existing conversation with the customer |
| `PHOTON_TEST_SENDER` | teammate's reference code | Not used by our code |
| `PHOTON_SIDECAR_URL` | `real_tools()`, sidecar port | `http://localhost:8787` |
| `API_URL` | sidecar | Where `/sessions/{id}/choice` lives |
| `ELEVENLABS_API_KEY` | voice, spikes | |
| `SCAMMER_AGENT_ID` | `elevenlabs_call.py` | Scammer Simulator agent |
| `ELEVENLABS_BANK_AGENT_ID` | callback | The "Safe Signal Follow-up" agent (renamed from "Lone Star Bank Fraud Team"; same ID). Persona is Safe Signal, never the bank; never asks for personal or account info or verifies identity; `transfer_to_number` set to `DEMO_BANK_NUMBER`. If `DEMO_BANK_NUMBER` changes, update the agent's transfer destination too |
| `ELEVENLABS_AGENT_ID` | teammate's reference code | Currently the same agent as `SCAMMER_AGENT_ID`; our code doesn't use it |
| `ELEVENLABS_PHONE_NUMBER_ID` | calls | The SIP-trunk number, `phnum_...` (see `elevenlabs_check.py`) |
| `DEMO_CUSTOMER_NUMBER` | everything | The phone every message and call goes to |
| `DEMO_BANK_NUMBER` | `DemoStore`, `PhotonComms.transfer`, follow-up agent | Lone Star Bank's verified number in the demo (a teammate's phone, R10). Must be E.164 (`+1...`); a placeholder like `+1XXXXXXXXXX` makes `real_tools()` fail with the variable's name |
| `DEMO_TRUSTED_CONTACT_NUMBER` | not used live | Trusted-contact messages also go to the customer number |

Photon has no SMS line on this project, so it cannot start an SMS by itself. SMS/RCS only happens through
Apple's fallback on the iMessage line.
