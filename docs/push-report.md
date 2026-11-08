# Push report: `l4-5-live-bridge`

2026-11-08, 09:30 CST. Base: `main` at `8594805`. Author: karthikyammanur (Lane 4, L4-5).
This file describes the latest push; overwrite it on the next one.

**In one line:** a live scam call can now feed Safe Signal end to end (call audio as transcript lines, plus a
real bank code from the customer's phone), but a full live Hero 1 run has not happened yet. Feature freeze is
10:00, so that run is the next thing to do.

## What this push contains

| Change | Files | State |
| --- | --- | --- |
| **Live bridge.** Places the Scammer Simulator call through ElevenLabs, polls its transcript every second, posts `call_start`, each line as a `turn`, then `call_end` to the API. Prints timing and length per line, never the text (R8). | `spikes/live_bridge.py` (new) | Ran one real call: all 15 lines reached the API |
| **Bank code from the phone.** `POST /live/sms {"sender_type", "org"}` turns a code that arrived on the customer's phone into an `sms_otp` event on the newest live call. Extra fields (such as the message text) are refused; with no live call it does nothing. | `services/api/main.py`, `services/api/hub.py`, test in `services/api/tests/test_api.py` | Tested (API tests 11/11) |
| **Call-screener Android app, first commit.** The "before" scene app (shows "Scam Likely" for numbers on `DEMO_SCAM_NUMBER`) plus a new SMS listener. When a text has a 4 to 8 digit code and a code word, it reports the sender type (5 or 6 digit sender = short code; `bank_shortcode` if the text names a bank) and the bank name. The code and the text never leave the phone. The app has an "API address" box. | `spikes/call-screener/` (new; `build/` and `local.properties` are git-ignored) | APK builds. Not yet installed on a phone |
| **Verification sweep script.** Checks 10 product claims against the API with mock tools and real Nemotron; writes evidence JSON to the system temp folder (alert wording and short flag quotes from synthetic fixtures, no full transcript lines). | `scripts/verify_claims.py` (new; previously untracked) | Not run in this session. **Fails ruff** (unused import `statistics`, unused variable `second`, formatting): pushed as is |
| **Local speech-to-text experiment.** Transcribes what the laptop plays (WASAPI loopback) and the mic with faster-whisper in 2 s chunks and prints `[caller]` / `[me]` lines. Prints only, writes nothing to disk. Not connected to the API. Possible plan B if ElevenLabs only gives the transcript after the call. | `listen.py` (new, repo root; its docstring says `scripts/listen.py`) | Not run in this session. Passes ruff; pyright would report 3 type errors, but the gate does not type-check the repo root. Needs `pyaudiowpatch`, `faster-whisper`, `numpy` |
| Docs: "Live Hero 1" setup section | `docs/integrations.md` | |
| New optional env vars: `DEMO_SCAM_NUMBER`, `SAFE_SIGNAL_PHONE_API_URL` | `.env.example` | |
| L4-5 owner set, status `doing` | `tasks.json` | |

### Changes outside the repo (teammates need to know)
- **New ElevenLabs agent: "Safe Signal Scammer Sim (Hero 1)".** The old Scammer Simulator ("Suspicious Bank
  Security Call") is told to stay a "security-awareness simulation" and "never request a real one-time code",
  so on the test call it said "I won't ask for any real codes" and Safe Signal correctly raised nothing. The new
  agent plays the Hero 1 script (fictional Lone Star Bank: flagged transfer, "don't hang up, don't call the
  branch", read back the code, then a "protected safe account"). The old agent is unchanged.
- **Your `.env`:** set `SCAMMER_AGENT_ID` to the new agent's ID (in the ElevenLabs workspace) to use it.

## Live test (one real call, session `live-test-1`)
- Call connected, ran 131 s, and all 15 transcript lines arrived at the API with call timestamps. `call_end` sent.
- Guardian: every Nemotron check succeeded (guard never paused) and raised no flags, which was correct for what
  the old agent said. No alerts, no after-call plan.
- **Not yet known:** whether ElevenLabs shows transcript lines while the call is still going, or only after it
  ends. The bridge now prints each line's call time next to the time it was sent, so the next call answers it.
  If lines only arrive at the end, polling is not enough and we need a live connection to ElevenLabs.

## What is needed for the full live Hero 1 run
1. Install the APK on the customer's phone (USB debugging + `adb install`, or send the APK), open it, allow SMS.
2. Run `ngrok http 8000` and put the URL in the app's API address box. The API listens only on localhost. The
   tunnel also exposes `WS /ws/{id}`, which streams live turn text, so stop it after the demo.
3. One person answers and plays the customer. When the scammer says a code is coming, trigger a real bank code
   (for example "forgot password" on a real bank's site). A code texted from a teammate's own number does not
   count: the signal watcher only reacts to bank short codes. **Never read the real code aloud**: ElevenLabs
   keeps the scammer call's transcript.
4. `python -u spikes/live_bridge.py --yes`

## Current state of the codebase

### Checks (`./checks/check.sh` on this branch)
| Gate | Result |
| --- | --- |
| Secrets (gitleaks) | Skipped: gitleaks not installed locally. Manual scan of this push: no keys; only fake 555 numbers |
| No audio or transcript files (R8) | Pass |
| ruff lint + format | **Fail**, only in `scripts/verify_claims.py` |
| pyright | Pass, 0 errors |
| Contracts and fixtures | 6 passed |
| Decision rules (R1, R4, R5, R6, R7) | 77 passed |
| Other Python tests | 212 passed |
| Eval scorer smoke test | Pass |

Pre-commit hooks are configured (`.pre-commit-config.yaml`) but not installed on this machine (LEAD-2 is open).

### Tasks (`tasks.json`)
| Lane | Done | Open |
| --- | --- | --- |
| Lead | | LEAD-1 contracts freeze, LEAD-2 repo/pre-commit, LEAD-3 PR reviews (all todo) |
| 1 Agents | L1-1 LLM client, L1-2 Guardian, L1-3 graph, L1-4 planner | L1-5 swap stand-ins for real tools (todo) |
| 2 Decision + data | L2-1, L2-2, L2-3, L2-4, L2-6 | L2-5 eval numbers (doing) |
| 3 Web | | L3-1 to L3-5 (all todo): no console, phone view or landing page yet |
| 4 Platform + demo | L4-1 spikes, L4-2 mocks | L4-3 API (doing), L4-4 real adapters + DB (todo), L4-5 live Hero 1 (doing), L4-6 video + Devpost (todo) |

### Gates (`PROGRESS.md`): none checked off
4:00am Hero 1 end to end and 7:00am eval numbers are past due. L4-5 was due 07:00. 10:00am feature freeze is next.

### What works today
- The full graph replays every fixture offline (tests), and hero1 also ran on live Nemotron (`PROGRESS.md`):
  nudge (t=40), whisper when the code arrives (t=92), alert with 3 buttons (t=101), then lock account,
  callback, recovery, evidence.
- The API takes live events (`/sessions/{id}/events`), the phone reply (`/choice`), the phone's bank code
  (`/live/sms`, new), and streams state over `WS /ws/{id}`. `TOOLS=real` uses the Photon and ElevenLabs adapters.
- Caller screen, signal watcher and `decide()` inside the graph are still the stand-ins in
  `services/agents/graph/stubs.py`; Lane 2's real versions are wired in by L1-5.

### Eval numbers (`evals/report.md`)
Only the Lane 2 baseline exists, measured with a keyword stand-in instead of the real Guardian: 47.1% catch at
`alert` (33/70) against an 80% target, 1.8% false alerts on benign calls (1/55). Gate failed. It has not been
re-run through the real graph yet (L2-5), so there is no number to quote on the Devpost.

### Known issues
- Guardian gives `policy_contradiction` 0.85 to a story-only first turn ("your number was used to open
  accounts"). Lead decision: leave as is (`PROGRESS.md`).
- `scripts/verify_claims.py` fails ruff (above).
- Transcript arrival during a live call is unverified (above).
- Consent for listening (F11) is still open.
