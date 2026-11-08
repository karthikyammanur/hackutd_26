# Lane 4: Platform, integrations and demo

**Best fit:** the person best at wiring APIs, debugging setup issues and talking to sponsors. Also owns the demo and Devpost, because both depend on knowing what actually works.
**Why one person:** every outside service (Brev, Photon, ElevenLabs, Tiger) breaks in its own way; one owner learns all of them once.

## You own
`spikes/`, `services/api/`, `services/agents/tools/`, `db/`, `deploy/`, `docs/demo-script.md`, `docs/devpost.md`

## You don't touch
`graph/`, `nodes/`, `llm.py` (Lane 1) · `decision/`, `signals/`, `data/`, `evals/` (Lane 2) · `apps/web/` (Lane 3) · `contracts/` (Lead)

## You consume
`contracts/interfaces.py` (`Comms`, `Voice`, `Store` you implement), `contracts/state.py` (`UIMessage`), `build_graph()` from Lane 1

## You produce
- Spikes (by 12am): Nemotron on Brev answering; a Photon call to a teammate's phone; an ElevenLabs voice line; answer F8 (can Photon join or end a live call?)
- `tools/`: `PhotonComms`, `ElevenLabsVoice`, `TigerStore` implementing the protocols, plus `mock.py` for everyone (by 12:30am)
- `services/api/`: FastAPI with `/sessions/{id}/replay` (fixture replay) and `/ws/{id}` (UIMessage stream); live mode feeds Photon/STT events into the graph
- `db/`: Tiger schema (events hypertable without `turn`, 24 h retention, evidence, pgvector policy index); the Indexer that loads T-Mobile pages
- Scammer Simulator script (Photon + ElevenLabs) for the live demo
- Deploys: web, API, model; GoDaddy domain (F7)

## Tasks (done-when)
1. **L4-1 Spikes** (by 12am): each spike prints a real response; F8 answered in `context/decisions.md`.
2. **L4-2 Mocks + protocols** (by 12:30am): `tools/mock.py` passes the protocol type check; Lane 1 imports it.
3. **L4-3 API replay** (by 2am): `/ws/{id}` streams `hero1_fake_bank.json` as `UIMessage`s; Lane 3 connects.
4. **L4-4 Real adapters + DB** (by 5am): Photon and ElevenLabs adapters work; events land in Tiger without `turn` rows.
5. **L4-5 Live Hero 1** (by 7am): a real call from the Scammer Simulator triggers an alert and a callback on a real phone.
6. **L4-6 Demo + Devpost** (by 11:30am): backup video recorded; Devpost lists each track's requirements and the feature that meets them.

## Rules that bite you most
R8, R9 (nothing conversational persisted), R14 (secrets), R10 (only teammates' numbers in the demo).
