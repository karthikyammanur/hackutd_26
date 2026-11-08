# Safe Signal API

## Quickstart
1. Run: `uvicorn services.api.main:app --port 8000` from the repo root (add `--reload` while developing; set `SAFE_SIGNAL_OFFLINE=1` to run without Nemotron, `TOOLS=real` in `.env` for live Photon and ElevenLabs instead of mocks).
2. Listen: open `ws://localhost:8000/ws/{session_id}`; every message is a `UIMessage` JSON (`type` = `event` | `trace` | `state`).
3. Replay (web dev): `POST /sessions/hero1_fake_bank/replay?speed=4` streams to `ws://localhost:8000/ws/fx_hero1_fake_bank`.
4. Live (bridge): `POST /sessions/{session_id}/events` with one contracts `Event` per request, starting with `call_start` and ending with `call_end`; returns 202 at once.
5. Customer reply: `POST /sessions/{session_id}/choice` with `{"choice": "1"}` (1 = call_bank, 2 = ask_trusted_contact, 3 = continue; names also work).

## Endpoints
| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | `ok`, whether the Nemotron URLs are set, session count |
| WS | `/ws/{session_id}` | Current `state` on connect (if the session exists), then live `event` / `trace` / `state` messages. Open it before or after the session starts. |
| POST | `/sessions/{session_id}/events` | Body: one `Event` (see `contracts/events.py`). `call_start` creates the session (`?offline=true` for no LLM). Other kinds need a running session (404), unknown kinds 422, `session_id` must match the URL (422), anything after `call_end` 409. Processed strictly in order. |
| POST | `/sessions/{session_id}/choice` | `{"choice": "1" \| "2" \| "3" \| "call_bank" \| "ask_trusted_contact" \| "continue" \| "dismiss", "digit"?: "1"}` (the sidecar's body; `digit` is used only if `choice` is not recognised, other extra fields are ignored). Stamped with the newest event's `t`. 404 unknown session, 409 after `call_end` (send it before `call_end` so aftercare can use it). |
| GET | `/sessions/{session_id}` | Current `SessionState` (for debugging the bridge). |
| POST | `/sessions/{fixture}/replay?speed=4&offline=false&choices=fixture` | Replays `evals/fixtures/{fixture}.json` paced by `t / speed`. `choices=live` skips the scripted `user_choice` so a phone tap drives it. Restarting a replay starts a fresh session. |

## Examples
```bash
curl -X POST localhost:8000/sessions/call_42/events -H 'Content-Type: application/json' \
  -d '{"session_id":"call_42","t":0,"source":"network","kind":"call_start","direction":"inbound","number":"+12145550147","first_seen":true}'
curl -X POST localhost:8000/sessions/call_42/events -H 'Content-Type: application/json' \
  -d '{"session_id":"call_42","t":12.5,"source":"network","kind":"turn","speaker":"caller","text":"Read me the code you just got."}'
curl -X POST localhost:8000/sessions/call_42/choice -H 'Content-Type: application/json' -d '{"choice":"1"}'
curl -X POST localhost:8000/sessions/call_42/events -H 'Content-Type: application/json' \
  -d '{"session_id":"call_42","t":95,"source":"network","kind":"call_end"}'
```
On Windows PowerShell use `curl.exe` with the body in a file (`-d "@event.json"`), or Git Bash.

## Rules the API keeps for you
- Turn text goes out only live, as it happens: never buffered for late listeners, never after `call_end` (R8).
- Graph-only fields (`transcript_window`, the current event) never appear in `state`.
- Nothing here hangs up a call (R2). If Nemotron fails, the session keeps going with `guard_paused` or template wording (R4).
- CORS allows `http://localhost:5173` (Vite) and `http://localhost:3000`.
