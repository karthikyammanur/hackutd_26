# Lane 4 start prompt: Platform, integrations and demo

```
You're my coding partner on Safe Signal (HackUTD 2026, T-Mobile track). I own lane 4: platform, integrations
and demo. Every outside service is unproven, so the first job is fast spikes that show what actually works.

Read first, in order: AGENTS.md, context/rules.md, context/lanes/lane-4-platform-demo.md, context/architecture.md,
context/decisions.md, contracts/ (all files), .env.example.

Hard boundaries:
- Edit only spikes/, services/api/, services/agents/tools/, db/, deploy/, docs/demo-script.md, docs/devpost.md
  (plus my rows in tasks.json and PROGRESS.md).
- contracts/ is frozen; implement contracts/interfaces.py exactly. If it can't fit a service, stop and tell me.
- Secrets only from .env (R14). Never write audio or transcript text to disk or the DB (R8). Demo calls go only
  to teammates' own numbers (R10). Nothing may hang up a customer's call (R2).
- Before writing code against Photon, ElevenLabs, Brev or Tiger Data, check their current docs; don't guess APIs.

Tonight, in this order:

1) L4-1 Spikes (each a standalone script in spikes/, reading .env, printing a real response):
   a. spikes/nemotron_brev.py: chat completion from Nemotron on Brev via the OpenAI-compatible API; print latency.
      Same script with the hosted NIM fallback URL.
   b. spikes/photon_call.py: through Photon (MCP), place a call to DEMO_CUSTOMER_NUMBER and send a message.
      Find out and write down: can Photon join an existing call, put one on hold, or warm-transfer? (F8)
   c. spikes/elevenlabs_voice.py: generate a short whisper line and play it on a Photon call if possible.
   d. spikes/tiger_db.py: connect to DATABASE_URL, create a hypertable, add a 24 h retention policy.
   Done when: each script prints a real result; F8's answer is written in context/decisions.md (tell me the text
   and I'll have the Lead merge it, since context/ is Lead-owned).

2) L4-2 services/agents/tools/mock.py: MockComms, MockVoice, MockStore implementing contracts/interfaces.py,
   recording every call in memory so tests can assert on them.
   Done when: pyright passes on tools/ and a tiny test calls each mock method.

3) L4-3 services/api/: FastAPI app with
   - GET /health
   - WS /ws/{session_id}: streams UIMessage JSON
   - POST /sessions/{fixture_name}/replay: replays evals/fixtures/<name>.json over the WebSocket, timed by `t`
   Done when: a WebSocket client (write a tiny one in spikes/) receives hero1's UIMessages in order.

Work style: plan first (3 to 6 lines + files you'll touch) and wait for my OK. Small commits. Name every assumption.
When each task is done: show the commands and their output, set its status to "done" in tasks.json, add one line
to PROGRESS.md, and commit with a message starting "L4-1:" etc.
```

## Next tasks (use the resume prompt)
- **L4-4** Real `PhotonComms`, `ElevenLabsVoice`, `TigerStore` (drops `turn` events); Indexer loading T-Mobile pages (official numbers, refund policy, what T-Mobile never asks) into pgvector.
- **L4-5** Live mode: Photon call audio → speech-to-text → events into the graph; Scammer Simulator script; Hero 1 on a real phone.
- **L4-6** Deploys (web, API, model), GoDaddy domain if entered, backup demo video, `docs/devpost.md` mapping each track's requirements to a feature.
