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
| `comms.call` | ElevenLabs outbound call from the **bank** agent to `DEMO_CUSTOMER_NUMBER`. The script is passed as dynamic variable `{{callback_script}}`, so the bank agent's prompt should use it |
| `comms.transfer` | Not supported (F8): raises, the step is marked failed, the call is untouched (R4) |
| `store.*` | `DemoStore`, in memory; drops `turn` events (R8). `DEMO_BANK_NUMBER` is Lone Star Bank's verified number |
| `account.hold_changes` | `SimAccount`: logs a simulated hold |

The callback refuses to run (`ToolConfigError`, nothing dialed) if `ELEVENLABS_BANK_AGENT_ID` is unset or
equals `SCAMMER_AGENT_ID`. Nothing ever dials 911, 988 or 112 (R1).

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
| `ELEVENLABS_BANK_AGENT_ID` | callback | Bank agent ("Lone Star Bank Fraud Team"). Its prompt does not use `{{callback_script}}` yet, so it ignores our script |
| `ELEVENLABS_AGENT_ID` | teammate's reference code | Currently the same agent as `SCAMMER_AGENT_ID`; our code doesn't use it |
| `ELEVENLABS_PHONE_NUMBER_ID` | calls | The SIP-trunk number, `phnum_...` (see `elevenlabs_check.py`) |
| `DEMO_CUSTOMER_NUMBER` | everything | The phone every message and call goes to |
| `DEMO_BANK_NUMBER` | `DemoStore` | Lone Star Bank's verified number in the demo |
| `DEMO_TRUSTED_CONTACT_NUMBER` | not used live | Trusted-contact messages also go to the customer number |

Photon has no SMS line on this project, so it cannot start an SMS by itself. SMS/RCS only happens through
Apple's fallback on the iMessage line.
